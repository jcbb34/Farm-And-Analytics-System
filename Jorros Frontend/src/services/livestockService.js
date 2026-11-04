import { schedulePayload, normalizeSchedule, assertMonitoringSaved } from "../components/Monitoring/monitoring.js";
import { httpClient } from "./httpClient.js";

function calculateAge(dateOfBirth) {
    if (!dateOfBirth) {
        return "Not specified";
    }

    const birthDate = new Date(`${dateOfBirth}T00:00:00`);

    if (Number.isNaN(birthDate.getTime())) {
        return "Not specified";
    }

    const today = new Date();

    let years =
        today.getFullYear() - birthDate.getFullYear();

    let months = today.getMonth() - birthDate.getMonth();

    if (today.getDate() < birthDate.getDate()) {
        months -= 1;
    }

    if (months < 0) {
        years -= 1;
        months += 12;
    }

    if (years > 0) {
        return `${years} ${years === 1 ? "Year" : "Years"}`;
    }

    return `${Math.max(months, 0)} ${months === 1 ? "Month" : "Months"}`;
}

function normalizeVaccinationRecord(record = {}) {
    return {
        id: record.id,

        livestockId:
            record.livestockId ??
            record.livestock_id,

        vaccine:
            record.vaccine ?? "",

        dateAdministered:
            record.dateAdministered ??
            record.date_administered ??
            "",

        nextDue:
            record.nextDue ??
            record.next_due ??
            "",

        status:
            record.status ??
            "Up to Date",

        administeredBy:
            record.administeredBy ??
            record.administered_by ??
            "",

        inventoryItemId:
            record.inventoryItemId ??
            record.inventory_item_id ??
            null,

        quantityUsed:
            record.quantityUsed ??
            record.quantity_used ??
            null,

        unit:
            record.unit ?? null,

        notes:
            record.notes ?? "",

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


function normalizeVaccinationSchedule(record = {}) {
    return {
        taskId: record.taskId ?? record.task_id ?? null,
        activityCode: record.activityCode ?? record.activity_code ?? null,
        title: record.title ?? "Vaccination",
        scheduledDate: record.scheduledDate ?? record.scheduled_date ?? "",
        status: record.status ?? "Scheduled",
        assignedEmployeeId: record.assignedEmployeeId ?? record.assigned_employee_id ?? null,
        assignedEmployeeName: record.assignedEmployeeName ?? record.assigned_employee_name ?? "",
        inventoryItemId: record.inventoryItemId ?? record.inventory_item_id ?? null,
        inventoryItemName: record.inventoryItemName ?? record.inventory_item_name ?? "",
        plannedQuantity: record.plannedQuantity ?? record.planned_quantity ?? null,
        plannedUnit: record.plannedUnit ?? record.planned_unit ?? null,
        actualQuantity: record.actualQuantity ?? record.actual_quantity ?? null,
        actualUnit: record.actualUnit ?? record.actual_unit ?? null,
        performedBy: record.performedBy ?? record.performed_by ?? "",
        completedAt: record.completedAt ?? record.completed_at ?? null,
        source: record.source ?? "Task Management",
    };
}


function normalizeFeedingRecord(record = {}) {
    return {
        id: record.id,
        livestockId:
            record.livestockId ??
            record.livestock_id,
        inventoryItemId:
            record.inventoryItemId ??
            record.inventory_item_id,
        feedingDate:
            record.feedingDate ??
            record.feeding_date ??
            "",
        feedingSlot:
            record.feedingSlot ??
            record.feeding_slot ??
            "",
        scheduledTimes:
            record.scheduledTimes ??
            record.scheduled_times ??
            "",
        feedType:
            record.feedType ??
            record.feed_type ??
            "",
        plannedQuantityKg: Number(
            record.plannedQuantityKg ??
            record.planned_quantity_kg ??
            0
        ),
        actualQuantityKg: Number(
            record.actualQuantityKg ??
            record.actual_quantity_kg ??
            0
        ),
        notes: record.notes ?? "",
        recordedByUserId:
            record.recordedByUserId ??
            record.recorded_by_user_id ??
            null,
        confirmedAt:
            record.confirmedAt ??
            record.confirmed_at ??
            null,
    };
}


function normalizeGrowthRecord(record = {}) {
    return {
        id: record.id,
        livestockId: record.livestockId ?? record.livestock_id,
        relatedTaskId: record.related_task_id ?? record.relatedTaskId ?? null,
        approvedByUserId: record.approved_by_user_id ?? record.approvedByUserId ?? null,
        measurementDate: record.measurementDate ?? record.measurement_date ?? "",
        weightKg: Number(record.weightKg ?? record.weight_kg ?? 0),
        animalsMeasured: record.animalsMeasured ?? record.animals_measured ?? null,
        totalMeasuredWeightKg: record.totalMeasuredWeightKg ?? record.total_measured_weight_kg ?? null,
        minWeightKg: record.minWeightKg ?? record.min_weight_kg ?? null,
        maxWeightKg: record.maxWeightKg ?? record.max_weight_kg ?? null,
        measurementBasis: record.measurementBasis ?? record.measurement_basis ?? "Average",
        previousWeightKg:
            record.previousWeightKg ?? record.previous_weight_kg ?? null,
        weightChangeKg:
            record.weightChangeKg ?? record.weight_change_kg ?? null,
        daysSincePrevious:
            record.daysSincePrevious ?? record.days_since_previous ?? null,
        averageDailyGainKg:
            record.averageDailyGainKg ?? record.average_daily_gain_kg ?? null,
        biologicalAgeDays: record.biologicalAgeDays ?? record.biological_age_days ?? null,
        expectedStage: record.expectedStage ?? record.expected_stage ?? null,
        expectedMinWeightKg: record.expectedMinWeightKg ?? record.expected_min_weight_kg ?? null,
        expectedMaxWeightKg: record.expectedMaxWeightKg ?? record.expected_max_weight_kg ?? null,
        growthProfileFamilyCode: record.growthProfileFamilyCode ?? record.growth_profile_family_code ?? null,
        growthProfileVersion: record.growthProfileVersion ?? record.growth_profile_version ?? null,
        growthProfileStatus: record.growthProfileStatus ?? record.growth_profile_status ?? null,
        deviationStatus: record.deviationStatus ?? record.deviation_status ?? null,
        deviationMessage: record.deviationMessage ?? record.deviation_message ?? null,
        notes: record.notes ?? "",
        recordedByUserId:
            record.recordedByUserId ?? record.recorded_by_user_id ?? null,
        createdAt: record.createdAt ?? record.created_at ?? null,
    };
}

function normalizeGrowthAssessment(record = {}) {
    return {
        asOfDate: record.asOfDate ?? record.as_of_date ?? "",
        ageDays: record.ageDays ?? record.age_days ?? null,
        ageSource: record.ageSource ?? record.age_source ?? "Unknown",
        currentStage: record.currentStage ?? record.current_stage ?? null,
        suggestedStage: record.suggestedStage ?? record.suggested_stage ?? null,
        suggestionReason: record.suggestionReason ?? record.suggestion_reason ?? "",
        expectedMinWeightKg: record.expectedMinWeightKg ?? record.expected_min_weight_kg ?? null,
        expectedMaxWeightKg: record.expectedMaxWeightKg ?? record.expected_max_weight_kg ?? null,
        deviationStatus: record.deviationStatus ?? record.deviation_status ?? null,
        deviationMessage: record.deviationMessage ?? record.deviation_message ?? null,
        profileId: record.profileId ?? record.profile_id ?? null,
        profileFamilyCode: record.profileFamilyCode ?? record.profile_family_code ?? null,
        profileVersion: record.profileVersion ?? record.profile_version ?? null,
        profileName: record.profileName ?? record.profile_name ?? null,
        profileStatus: record.profileStatus ?? record.profile_status ?? null,
        approvalStatus: record.approvalStatus ?? record.approval_status ?? null,
        sourceTitle: record.sourceTitle ?? record.source_title ?? null,
        sourceUrl: record.sourceUrl ?? record.source_url ?? null,
    };
}

function normalizePen(record = {}) {
    return {
        id: record.id,
        name:
            record.name ??
            record.penName ??
            record.pen_name ??
            "",
        purpose:
            record.purpose ??
            "General",
        animalType:
            record.animalType ??
            record.animal_type ??
            "",
        capacity:
            record.capacity == null
                ? null
                : Number(record.capacity),
        currentOccupancy: Number(record.currentOccupancy ?? record.current_occupancy ?? 0),
        availableCapacity:
            record.availableCapacity ?? record.available_capacity ?? null,
        locationArea:
            record.locationArea ??
            record.location_area ??
            "",
        status:
            record.status ??
            "Active",
        notes:
            record.notes ??
            "",
        isArchived:
            Boolean(
                record.isArchived ??
                record.is_archived ??
                false
            ),
        createdAt:
            record.createdAt ??
            record.created_at ??
            null,
        updatedAt:
            record.updatedAt ??
            record.updated_at ??
            null,
    };
}

function normalizeLivestock(record = {}) {
    const dateOfBirth =
        record.dateOfBirth ??
        record.date_of_birth ??
        "";

    const vaccinationRecords =
        record.vaccinationRecords ??
        record.vaccination_records ??
        [];

    const feedingRecords =
        record.feedingRecords ??
        record.feeding_records ??
        [];

    const growthRecords =
        record.growthRecords ??
        record.growth_records ??
        [];

    return {
        ...normalizeSchedule(record),
        id: record.id,

        animalId:
            record.animalId ??
            record.animalCode ??
            record.animal_code ??
            "",

        recordName:
            record.recordName ??
            record.record_name ??
            "",

        type:
            record.type ??
            record.animalType ??
            record.animal_type ??
            "",

        breed:
            record.breed ?? "",

        quantity:
            Number(record.quantity ?? 1),

        sex:
            record.sex ?? "Mixed",

        recordType: record.recordType ?? record.record_type ?? "Batch",
        lifecycleStatus: record.lifecycleStatus ?? record.lifecycle_status ?? "Active",
        penId: record.penId ?? record.pen_id ?? null,
        originLivestockId: record.originLivestockId ?? record.origin_livestock_id ?? null,
        maleQuantity: Number(record.maleQuantity ?? record.male_quantity ?? 0),
        femaleQuantity: Number(record.femaleQuantity ?? record.female_quantity ?? 0),
        unknownSexQuantity: Number(record.unknownSexQuantity ?? record.unknown_sex_quantity ?? 0),

        dateOfBirth,
        ageIsEstimated: Boolean(record.ageIsEstimated ?? record.age_is_estimated ?? false),
        estimatedAgeDays: record.estimatedAgeDays ?? record.estimated_age_days ?? null,
        estimatedAgeAsOfDate: record.estimatedAgeAsOfDate ?? record.estimated_age_as_of_date ?? "",
        estimatedAgeConfidence: record.estimatedAgeConfidence ?? record.estimated_age_confidence ?? "",
        estimatedAgeSource: record.estimatedAgeSource ?? record.estimated_age_source ?? "",
        acquisitionStage: record.acquisitionStage ?? record.acquisition_stage ?? "",
        acquisitionVaccinationHistory: record.acquisitionVaccinationHistory ?? record.acquisition_vaccination_history ?? "",
        acquisitionTreatmentHistory: record.acquisitionTreatmentHistory ?? record.acquisition_treatment_history ?? "",
        medicalHistoryStatus: record.medicalHistoryStatus ?? record.medical_history_status ?? "Unknown - Needs Review",
        feedingPlanName: record.feedingPlanName ?? record.feeding_plan_name ?? "",
        assignedEmployeeId: record.assignedEmployeeId ?? record.assigned_employee_id ?? null,
        careTemplateId: record.careTemplateId ?? record.care_template_id ?? null,
        careProtocolName: record.careProtocolName ?? record.care_protocol_name ?? null,
        careProtocolVersion: record.careProtocolVersion ?? record.care_protocol_version ?? null,
        careProtocolStatus: record.careProtocolStatus ?? record.care_protocol_status ?? null,

        age:
            record.age ??
            calculateAge(dateOfBirth),

        weight:
            Number(
                record.weight ??
                record.weightKg ??
                record.weight_kg ??
                0
            ),
        minWeight: record.minWeight ?? record.min_weight_kg ?? null,
        maxWeight: record.maxWeight ?? record.max_weight_kg ?? null,

        penLocation:
            record.penLocation ??
            record.pen_location ??
            "",

        healthStatus:
            record.healthStatus ??
            record.health_status ??
            "Healthy",
        healthyQuantity: Number(record.healthyQuantity ?? record.healthy_quantity ?? 0),
        atRiskQuantity: Number(record.atRiskQuantity ?? record.at_risk_quantity ?? 0),
        sickQuantity: Number(record.sickQuantity ?? record.sick_quantity ?? 0),
        underTreatmentQuantity: Number(record.underTreatmentQuantity ?? record.under_treatment_quantity ?? 0),

        growthStatus:
            record.growthStatus ??
            record.growth_status ??
            "Growing",
        productionPurpose: record.productionPurpose ?? record.production_purpose ?? "General",

        lastCheckup:
            record.lastCheckup ??
            record.last_checkup ??
            "",

        healthNotes:
            record.healthNotes ??
            record.health_notes ??
            "",

        vaccinationStatus:
            record.vaccinationStatus ??
            record.vaccination_status ??
            "Not Vaccinated",

        nextVaccination:
            record.nextVaccination ??
            record.next_vaccination ??
            "",

        feedingSlots: record.feedingSlots ?? record.feeding_slots ?? [],
        feedingSchedule: {
            times:
                record.feedingSchedule?.times ??
                record.feedTimes ??
                record.feed_times ??
                "Not specified",

            feedType:
                record.feedingSchedule?.feedType ??
                record.feedType ??
                record.feed_type ??
                "Not specified",

            dailyAmountKg:
                Number(
                    record.feedingSchedule?.dailyAmountKg ??
                    record.dailyFeedKg ??
                    record.daily_feed_kg ??
                    0
                ),

            notes:
                record.feedingSchedule?.notes ??
                record.feedingNotes ??
                record.feeding_notes ??
                "No feeding notes.",
        },

        feedInventoryItemId:
            record.feedInventoryItemId ??
            record.feed_inventory_item_id ??
            null,

        productionOutput:
            record.productionOutput ??
            record.production_output ??
            "",

        dateAcquired:
            record.dateAcquired ??
            record.date_acquired ??
            "",

        acquiredFrom:
            record.acquiredFrom ??
            record.acquired_from ??
            "",

        isNewBirth:
            record.isNewBirth ?? false,

        vaccinationRecords:
            vaccinationRecords.map(
                normalizeVaccinationRecord
            ),

        feedingRecords:
            feedingRecords.map(
                normalizeFeedingRecord
            ),

        growthRecords:
            growthRecords.map(
                normalizeGrowthRecord
            ),

        isArchived:
            Boolean(
                record.isArchived ??
                record.is_archived ??
                false
            ),

        createdByUserId:
            record.createdByUserId ??
            record.created_by_user_id ??
            null,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,

        updatedAt:
            record.updatedAt ??
            record.updated_at ??
            null,
    };
}

function createLivestockPayload(data = {}) {
    const feedingSchedule =
        data.feedingSchedule ?? {};

    return {
        ...schedulePayload(data),
        record_name:
            data.recordName?.trim() ?? "",

        animal_type:
            data.type?.trim() ?? "",

        breed:
            data.breed?.trim() ?? "",

        quantity:
            Number(data.quantity ?? 1),

        sex:
            data.sex ?? "Mixed",
        record_type: data.recordType ?? "Batch",
        lifecycle_status: data.lifecycleStatus ?? "Active",
        pen_id: data.penId ? Number(data.penId) : null,
        male_quantity: Number(data.maleQuantity ?? 0),
        female_quantity: Number(data.femaleQuantity ?? 0),
        unknown_sex_quantity: Number(data.unknownSexQuantity ?? 0),

        date_of_birth:
            data.dateOfBirth || null,
        age_is_estimated: Boolean(data.ageIsEstimated),
        estimated_age_days: data.estimatedAgeDays === "" || data.estimatedAgeDays == null ? null : Number(data.estimatedAgeDays),
        estimated_age_as_of_date: data.estimatedAgeAsOfDate || null,
        estimated_age_confidence: data.estimatedAgeConfidence || null,
        estimated_age_source: data.estimatedAgeSource?.trim() || null,
        acquisition_stage: data.acquisitionStage || data.growthStatus || null,
        acquisition_vaccination_history: data.acquisitionVaccinationHistory?.trim() || null,
        acquisition_treatment_history: data.acquisitionTreatmentHistory?.trim() || null,
        feeding_plan_name: data.feedingPlanName?.trim() || null,
        assigned_employee_id: data.assignedEmployeeId ? Number(data.assignedEmployeeId) : null,
        care_template_id: data.careTemplateId ? Number(data.careTemplateId) : null,

        weight_kg:
            Number(data.weight ?? 0),
        min_weight_kg: data.minWeight ? Number(data.minWeight) : null,
        max_weight_kg: data.maxWeight ? Number(data.maxWeight) : null,

        pen_location:
            data.penLocation?.trim() ?? "",

        health_status:
            data.healthStatus ?? "Healthy",
        healthy_quantity: Number(data.healthyQuantity ?? 0),
        at_risk_quantity: Number(data.atRiskQuantity ?? 0),
        sick_quantity: Number(data.sickQuantity ?? 0),
        under_treatment_quantity: Number(data.underTreatmentQuantity ?? 0),

        growth_status:
            data.growthStatus ?? "Growing",
        production_purpose: data.productionPurpose ?? "General",

        last_checkup:
            data.lastCheckup || null,

        health_notes:
            data.healthNotes?.trim() || null,

        vaccination_status:
            data.vaccinationStatus ??
            "Not Vaccinated",

        next_vaccination:
            data.nextVaccination || null,

        feed_times:
            feedingSchedule.times?.trim() || null,

        feed_type:
            feedingSchedule.feedType?.trim() || null,

        daily_feed_kg:
            Number(
                feedingSchedule.dailyAmountKg ?? 0
            ),

        feeding_notes:
            feedingSchedule.notes?.trim() || null,

        feed_inventory_item_id:
            data.feedInventoryItemId || null,

        production_output:
            data.productionOutput?.trim() || null,

        date_acquired:
            data.dateAcquired,

        acquired_from:
            data.acquiredFrom?.trim() || null,
    };
}

function createUpdatePayload(data = {}) {
    const payload = {};

    const assignText = (
        frontendKey,
        backendKey
    ) => {
        if (data[frontendKey] !== undefined) {
            payload[backendKey] =
                data[frontendKey] === null
                    ? null
                    : String(data[frontendKey]).trim() || null;
        }
    };

    assignText("recordName", "record_name");
    assignText("type", "animal_type");
    assignText("breed", "breed");
    assignText("sex", "sex");
    assignText("recordType", "record_type");
    assignText("lifecycleStatus", "lifecycle_status");
    assignText("productionPurpose", "production_purpose");
    assignText("penLocation", "pen_location");
    assignText("healthNotes", "health_notes");
    assignText("productionOutput", "production_output");
    assignText("acquiredFrom", "acquired_from");

    if (data.quantity !== undefined) {
        payload.quantity = Number(data.quantity);
    }

    if (data.penId !== undefined) payload.pen_id = data.penId ? Number(data.penId) : null;
    for (const [front, back] of [
        ["maleQuantity", "male_quantity"],
        ["femaleQuantity", "female_quantity"],
        ["unknownSexQuantity", "unknown_sex_quantity"],
        ["healthyQuantity", "healthy_quantity"],
        ["atRiskQuantity", "at_risk_quantity"],
        ["sickQuantity", "sick_quantity"],
        ["underTreatmentQuantity", "under_treatment_quantity"],
    ]) {
        if (data[front] !== undefined) payload[back] = Number(data[front]);
    }

    if (data.minWeight !== undefined) payload.min_weight_kg = data.minWeight ? Number(data.minWeight) : null;
    if (data.maxWeight !== undefined) payload.max_weight_kg = data.maxWeight ? Number(data.maxWeight) : null;

    if (data.dateOfBirth !== undefined) {
        payload.date_of_birth =
            data.dateOfBirth || null;
    }
    if (data.ageIsEstimated !== undefined) payload.age_is_estimated = Boolean(data.ageIsEstimated);
    if (data.estimatedAgeDays !== undefined) payload.estimated_age_days = data.estimatedAgeDays === "" || data.estimatedAgeDays == null ? null : Number(data.estimatedAgeDays);
    if (data.estimatedAgeAsOfDate !== undefined) payload.estimated_age_as_of_date = data.estimatedAgeAsOfDate || null;
    if (data.estimatedAgeConfidence !== undefined) payload.estimated_age_confidence = data.estimatedAgeConfidence || null;
    if (data.estimatedAgeSource !== undefined) payload.estimated_age_source = data.estimatedAgeSource?.trim() || null;
    if (data.acquisitionStage !== undefined) payload.acquisition_stage = data.acquisitionStage || null;
    if (data.acquisitionVaccinationHistory !== undefined) payload.acquisition_vaccination_history = data.acquisitionVaccinationHistory?.trim() || null;
    if (data.acquisitionTreatmentHistory !== undefined) payload.acquisition_treatment_history = data.acquisitionTreatmentHistory?.trim() || null;
    if (data.feedingPlanName !== undefined) payload.feeding_plan_name = data.feedingPlanName?.trim() || null;
    if (data.assignedEmployeeId !== undefined) payload.assigned_employee_id = data.assignedEmployeeId ? Number(data.assignedEmployeeId) : null;
    if (data.careTemplateId !== undefined) payload.care_template_id = data.careTemplateId ? Number(data.careTemplateId) : null;
    if (data.futureCareTaskAction) payload.future_care_task_action = data.futureCareTaskAction;

    if (data.weight !== undefined) {
        payload.weight_kg =
            Number(data.weight);
    }

    if (data.healthStatus !== undefined) {
        payload.health_status =
            data.healthStatus;
    }

    if (data.growthStatus !== undefined) {
        payload.growth_status =
            data.growthStatus;
    }

    if (data.lastCheckup !== undefined) {
        payload.last_checkup =
            data.lastCheckup || null;
    }

    if (data.vaccinationStatus !== undefined) {
        payload.vaccination_status =
            data.vaccinationStatus;
    }

    if (data.nextVaccination !== undefined) {
        payload.next_vaccination =
            data.nextVaccination || null;
    }

    if (data.dateAcquired !== undefined) {
        payload.date_acquired =
            data.dateAcquired || null;
    }

    if (data.feedInventoryItemId !== undefined) {
        payload.feed_inventory_item_id =
            data.feedInventoryItemId || null;
    }

    if (data.feedingSchedule !== undefined) {
        const feedingSchedule =
            data.feedingSchedule ?? {};

        payload.feed_times =
            feedingSchedule.times?.trim() || null;

        payload.feed_type =
            feedingSchedule.feedType?.trim() || null;

        payload.daily_feed_kg = Number(
            feedingSchedule.dailyAmountKg ?? 0
        );

        payload.feeding_notes =
            feedingSchedule.notes?.trim() || null;
    }

    if (["monitoringEnabled", "monitoringStartDate", "monitoringEndDate", "monitoringFrequencyDays"].some((key) => data[key] !== undefined)) Object.assign(payload, schedulePayload(data));
    return payload;
}

async function verifySavedMonitoring(payload, response) {
    const record = response?.data ?? response;
    if (!Object.hasOwn(payload, "monitoring_enabled")) return record;
    // Older backend processes can silently ignore new request fields. Check
    // the write response and a new read before the UI announces success.
    assertMonitoringSaved(payload, record);
    const refreshed = await httpClient.get(`/livestock/${record.id}`, { cache: "no-store" });
    const saved = refreshed?.data ?? refreshed;
    assertMonitoringSaved(payload, saved);
    return saved;
}

export const livestockService =
    Object.freeze({
        async getLivestock(
            includeArchived = false
        ) {
            const response =
                await httpClient.get(
                    "/livestock",
                    {
                        cache: "no-store",
                        query: {
                            include_archived:
                                includeArchived,
                        },
                    }
                );

            const records =
                Array.isArray(response)
                    ? response
                    : response?.data ?? [];

            return records.map(
                normalizeLivestock
            );
        },

        async getPens(
            includeArchived = false
        ) {
            const response =
                await httpClient.get(
                    "/livestock/pens",
                    {
                        query: {
                            include_archived:
                                includeArchived,
                        },
                    }
                );

            const records =
                Array.isArray(response)
                    ? response
                    : response?.data ?? [];

            return records.map(normalizePen);
        },


        async createPen(data) {
            const response = await httpClient.post("/livestock/pens", {
                name: data.name?.trim(),
                purpose: data.purpose || "General",
                animal_type: data.animalType || null,
                capacity: data.capacity ? Number(data.capacity) : null,
                location_area: data.locationArea?.trim() || null,
                status: data.status || "Active",
                notes: data.notes?.trim() || null,
            });
            return normalizePen(response?.data ?? response);
        },

        async updatePen(penId, data) {
            const response = await httpClient.put(`/livestock/pens/${penId}`, {
                name: data.name?.trim(),
                purpose: data.purpose || "General",
                animal_type: data.animalType || null,
                capacity: data.capacity ? Number(data.capacity) : null,
                location_area: data.locationArea?.trim() || null,
                status: data.status || "Active",
                notes: data.notes?.trim() || null,
            });
            return normalizePen(response?.data ?? response);
        },

        async transferPen(livestockId, data) {
            const response = await httpClient.post(`/livestock/${livestockId}/transfer-pen`, {
                pen_id: Number(data.penId),
                event_date: data.eventDate,
                reason: data.reason?.trim() || null,
            });
            return normalizeLivestock(response?.data ?? response);
        },

        async splitBatch(livestockId, data) {
            const response = await httpClient.post(`/livestock/${livestockId}/split-batch`, {
                quantity: Number(data.quantity),
                record_name: data.recordName?.trim() || null,
                pen_id: data.penId ? Number(data.penId) : null,
                event_date: data.eventDate,
                reason: data.reason?.trim() || null,
                male_quantity: Number(data.maleQuantity ?? 0),
                female_quantity: Number(data.femaleQuantity ?? 0),
                unknown_sex_quantity: Number(data.unknownSexQuantity ?? 0),
                healthy_quantity: Number(data.healthyQuantity ?? 0),
                at_risk_quantity: Number(data.atRiskQuantity ?? 0),
                sick_quantity: Number(data.sickQuantity ?? 0),
                under_treatment_quantity: Number(data.underTreatmentQuantity ?? 0),
            });
            return normalizeLivestock(response?.data ?? response);
        },
        async getVaccinationSchedule(livestockId) {
            const response = await httpClient.get(`/livestock/${livestockId}/vaccination-schedule`);
            const records = Array.isArray(response) ? response : response?.data ?? [];
            return records.map(normalizeVaccinationSchedule);
        },

        async getLivestockRecord(
            livestockId
        ) {
            const response =
                await httpClient.get(
                    `/livestock/${livestockId}`,
                    { cache: "no-store" }
                );

            return normalizeLivestock(
                response?.data ?? response
            );
        },

        async createLivestock(data, { idempotencyKey } = {}) {
            const payload = createLivestockPayload(data);
            const response =
                await httpClient.post(
                    "/livestock",
                    payload,
                    {
                        headers: idempotencyKey
                            ? { "Idempotency-Key": idempotencyKey }
                            : {},
                    }
                );

            return normalizeLivestock(
                await verifySavedMonitoring(payload, response)
            );
        },

        async updateLivestock(
            livestockId,
            data
        ) {
            const payload = createUpdatePayload(data);
            const response =
                await httpClient.put(
                    `/livestock/${livestockId}`,
                    payload
                );

            return normalizeLivestock(
                await verifySavedMonitoring(payload, response)
            );
        },

        async previewGrowthAssessment(data = {}) {
            const response = await httpClient.post("/livestock/growth-assessment/preview", {
                animal_type: data.type || data.animalType || "",
                breed: data.breed?.trim() || null,
                production_purpose: data.productionPurpose || null,
                sex: data.sex || null,
                date_of_birth: data.dateOfBirth || null,
                estimated_age_days: data.estimatedAgeDays === "" || data.estimatedAgeDays == null ? null : Number(data.estimatedAgeDays),
                estimated_age_as_of_date: data.estimatedAgeAsOfDate || null,
                weight_kg: data.weight ? Number(data.weight) : null,
            });
            return normalizeGrowthAssessment(response?.data ?? response);
        },

        async getGrowthAssessment(livestockId) {
            const response = await httpClient.get(`/livestock/${livestockId}/growth-assessment`);
            return normalizeGrowthAssessment(response?.data ?? response);
        },

        async overrideGrowthStage(livestockId, stage, reason) {
            const response = await httpClient.post(`/livestock/${livestockId}/growth-stage-override`, {
                stage,
                reason: reason?.trim() || "",
            });
            return normalizeGrowthAssessment(response?.data ?? response);
        },

        async archiveLivestock(
            livestockId
        ) {
            const response =
                await httpClient.post(
                    `/livestock/${livestockId}/archive`,
                    {}
                );

            return normalizeLivestock(
                response?.data ?? response
            );
        },

        async restoreLivestock(
            livestockId
        ) {
            const response =
                await httpClient.post(
                    `/livestock/${livestockId}/restore`,
                    {}
                );

            return normalizeLivestock(
                response?.data ?? response
            );
        },

        async addVaccinationRecord(
            livestockId,
            data,
            { idempotencyKey = null } = {}
        ) {
            const response =
                await httpClient.post(
                    `/livestock/${livestockId}/vaccination-records`,
                    {
                        vaccine:
                            data.vaccine?.trim() ?? "",

                        date_administered:
                            data.dateAdministered,

                        next_due:
                            data.nextDue || null,

                        status:
                            data.status ??
                            "Up to Date",

                        administered_by:
                            data.administeredBy?.trim() ||
                            null,

                        inventory_item_id: data.inventoryItemId ? Number(data.inventoryItemId) : null,
                        quantity_used: data.quantityUsed ? Number(data.quantityUsed) : null,
                        notes:
                            data.notes?.trim() || null,
                    },
                    { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} }
                );

            return normalizeVaccinationRecord(
                response?.data ?? response
            );
        },

        async addGrowthRecord(
            livestockId,
            data
        ) {
            const response =
                await httpClient.post(
                    `/livestock/${livestockId}/growth-records`,
                    {
                        measurement_date: data.measurementDate,
                        weight_kg: Number(data.weightKg),
                        animals_measured: data.animalsMeasured ? Number(data.animalsMeasured) : null,
                        total_measured_weight_kg: data.totalMeasuredWeightKg ? Number(data.totalMeasuredWeightKg) : null,
                        min_weight_kg: data.minWeightKg ? Number(data.minWeightKg) : null,
                        max_weight_kg: data.maxWeightKg ? Number(data.maxWeightKg) : null,
                        measurement_basis: data.measurementBasis || "Average",
                        notes: data.notes?.trim() || null,
                    }
                );

            return normalizeGrowthRecord(
                response?.data ?? response
            );
        },

        async confirmFeeding(
            livestockId,
            data,
            idempotencyKey = null
        ) {
            const response =
                await httpClient.post(
                    `/livestock/${livestockId}/feeding-records`,
                    {
                        inventory_item_id:
                            Number(data.inventoryItemId),
                        feeding_date:
                            data.feedingDate,
                        feeding_slot:
                            data.feedingSlot?.trim() ?? "",
                        actual_quantity_kg:
                            data.actualQuantityKg
                                ? Number(data.actualQuantityKg)
                                : null,
                        notes:
                            data.notes?.trim() || null,
                    },
                    {
                        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
                    }
                );

            return normalizeFeedingRecord(
                response?.data ?? response
            );
        },
    });
