import { loadEventResources } from './eventPlanningService.js';
import { httpClient } from "./httpClient.js";

const inFlightActivityRequests = new Map();
let automaticSyncRequest = null;
const inFlightActivityMutations = new Map();

function createActivityRequestKey(
    includeArchived,
    dateFrom,
    dateTo
) {
    return JSON.stringify({
        includeArchived: Boolean(includeArchived),
        dateFrom: dateFrom || "",
        dateTo: dateTo || "",
    });
}

function dateOnly(value) {
    if (!value) {
        return "";
    }

    return String(value).slice(0, 10);
}

function timeOnly(value) {
    if (!value) {
        return "";
    }

    return String(value).slice(0, 5);
}

function normalizeStatus(value) {
    if (value === "Upcoming") {
        return "Pending";
    }

    return value || "Pending";
}

function normalizeActivity(record = {}) {
    return {
        id: record.id,

        activityCode:
            record.activityCode ??
            record.activity_code ??
            "",

        name: record.name ?? "",
        category: record.category ?? "Other",

        relatedTo:
            record.relatedTo ??
            record.related_to ??
            "",

        location: record.location ?? "",
        description: record.description ?? "",

        date: dateOnly(
            record.date ??
                record.activityDate ??
                record.activity_date
        ),

        startTime: timeOnly(
            record.startTime ??
                record.start_time
        ),

        endTime: timeOnly(
            record.endTime ??
                record.end_time
        ),

        duration: record.duration ?? "",

        assignedBy:
            record.assignedBy ??
            record.assigned_by ??
            "",

        assignedTo:
            record.assignedTo ??
            record.assigned_to ??
            "",
        assignedEmployeeId:
            record.assignedEmployeeId ??
            record.assigned_employee_id ??
            null,
        instructions: record.instructions ?? "",
        requiresReview: Boolean(record.requiresReview ?? record.requires_review ?? false),
        requiresEvidence: Boolean(record.requiresEvidence ?? record.requires_evidence ?? false),
        plannedQuantity: record.plannedQuantity ?? record.planned_quantity ?? null,
        plannedUnit: record.plannedUnit ?? record.planned_unit ?? "",
        recurringRule: record.recurringRule ?? record.recurring_rule ?? "",
        problemReport: record.problemReport ?? record.problem_report ?? "",
        needsReassignment: Boolean(record.needsReassignment ?? record.needs_reassignment ?? false),

        status: normalizeStatus(record.status),
        priority: record.priority ?? "Medium",

        isAutomatic: Boolean(
            record.isAutomatic ??
                record.is_automatic ??
                false
        ),
        sourceModule:
            record.sourceModule ??
            record.source_module ??
            "",
        sourceType:
            record.sourceType ??
            record.source_type ??
            "",
        sourceRecordId:
            record.sourceRecordId ??
            record.source_record_id ??
            null,
        sourcePath:
            record.sourcePath ??
            record.source_path ??
            "",

        workflowType:
            record.workflowType ??
            record.workflow_type ??
            "standalone_activity",
        linkedTaskId:
            record.linkedTaskId ??
            record.linked_task_id ??
            null,
        availableActions: Array.isArray(
            record.availableActions ?? record.available_actions
        )
            ? [...(record.availableActions ?? record.available_actions)]
            : [],
        canCompleteDirectly: Boolean(
            record.canCompleteDirectly ??
            record.can_complete_directly ??
            false
        ),
        requiresEmployeeSubmission: Boolean(
            record.requiresEmployeeSubmission ??
            record.requires_employee_submission ??
            false
        ),
        requiresManagerReview: Boolean(
            record.requiresManagerReview ??
            record.requires_manager_review ??
            false
        ),

        isArchived: Boolean(
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

function createActivityPayload(data = {}) {
    const location =
        data.location?.trim() ||
        "Joross Farm";

    return {
        name:
            data.name?.trim() ||
            data.title?.trim() ||
            "Farm Activity",

        category:
            data.category?.trim() ||
            data.type?.trim() ||
            "Other",

        related_to:
            data.relatedTo?.trim() ||
            data.related_to?.trim() ||
            location ||
            "General Farm",

        location,

        description:
            data.description?.trim() ||
            null,

        activity_date:
            data.date ??
            data.activityDate ??
            data.activity_date,

        start_time:
            data.startTime ??
            data.start_time,

        end_time:
            data.endTime ||
            data.end_time ||
            null,

        duration:
            data.duration?.trim() ||
            null,

        assigned_by:
            data.assignedBy?.trim() ||
            data.assigned_by?.trim() ||
            "Farm Manager",

        assigned_to:
            data.assignedTo?.trim() ||
            data.assigned_to?.trim() ||
            "Unassigned",
        assigned_employee_id: data.assignedEmployeeId ?? data.assigned_employee_id ?? null,
        instructions: data.instructions?.trim() || null,
        requires_review: Boolean(data.requiresReview ?? data.requires_review ?? false),
        requires_evidence: Boolean(data.requiresEvidence ?? data.requires_evidence ?? false),
        planned_quantity: data.plannedQuantity ?? data.planned_quantity ?? null,
        planned_unit: data.plannedUnit?.trim() || data.planned_unit?.trim() || null,
        planned_inventory_item_id: data.plannedInventoryItemId ?? data.planned_inventory_item_id ?? null,
        planned_usage_type: data.plannedUsageType ?? data.planned_usage_type ?? null,
        source_module: data.sourceModule ?? data.source_module ?? null,
        source_type: data.sourceType ?? data.source_type ?? null,
        source_record_id: data.sourceRecordId ?? data.source_record_id ?? null,
        source_path: data.sourcePath ?? data.source_path ?? null,
        feeding_slot: data.feedingSlot || data.feeding_slot || null,
        recurring_rule: data.recurringRule?.trim() || data.recurring_rule?.trim() || null,

        status: normalizeStatus(data.status),
        priority: data.priority || "Medium",
    };
}

function createUpdatePayload(data = {}) {
    const payload = {};

    if (data.name !== undefined || data.title !== undefined) {
        payload.name =
            data.name?.trim() ||
            data.title?.trim() ||
            "Farm Activity";
    }

    if (data.category !== undefined || data.type !== undefined) {
        payload.category =
            data.category?.trim() ||
            data.type?.trim() ||
            "Other";
    }

    if (
        data.relatedTo !== undefined ||
        data.related_to !== undefined
    ) {
        payload.related_to =
            data.relatedTo?.trim() ||
            data.related_to?.trim() ||
            "General Farm";
    }

    if (data.location !== undefined) {
        payload.location =
            data.location?.trim() ||
            "Jorros Farm";
    }

    if (data.description !== undefined) {
        payload.description =
            data.description?.trim() ||
            null;
    }

    if (
        data.date !== undefined ||
        data.activityDate !== undefined ||
        data.activity_date !== undefined
    ) {
        payload.activity_date =
            data.date ??
            data.activityDate ??
            data.activity_date;
    }

    if (
        data.startTime !== undefined ||
        data.start_time !== undefined
    ) {
        payload.start_time =
            data.startTime ??
            data.start_time;
    }

    if (
        data.endTime !== undefined ||
        data.end_time !== undefined
    ) {
        payload.end_time =
            data.endTime ||
            data.end_time ||
            null;
    }

    if (data.duration !== undefined) {
        payload.duration =
            data.duration?.trim() ||
            null;
    }

    if (
        data.assignedBy !== undefined ||
        data.assigned_by !== undefined
    ) {
        payload.assigned_by =
            data.assignedBy?.trim() ||
            data.assigned_by?.trim() ||
            "Farm Manager";
    }

    if (
        data.assignedTo !== undefined ||
        data.assigned_to !== undefined
    ) {
        payload.assigned_to =
            data.assignedTo?.trim() ||
            data.assigned_to?.trim() ||
            "Unassigned";
    }

    if (data.assignedEmployeeId !== undefined || data.assigned_employee_id !== undefined) {
        payload.assigned_employee_id = data.assignedEmployeeId ?? data.assigned_employee_id ?? null;
    }
    if (data.instructions !== undefined) payload.instructions = data.instructions?.trim() || null;
    if (data.requiresReview !== undefined || data.requires_review !== undefined) payload.requires_review = Boolean(data.requiresReview ?? data.requires_review);
    if (data.requiresEvidence !== undefined || data.requires_evidence !== undefined) payload.requires_evidence = Boolean(data.requiresEvidence ?? data.requires_evidence);
    if (data.plannedQuantity !== undefined || data.planned_quantity !== undefined) payload.planned_quantity = data.plannedQuantity ?? data.planned_quantity ?? null;
    if (data.plannedUnit !== undefined || data.planned_unit !== undefined) payload.planned_unit = data.plannedUnit?.trim() || data.planned_unit?.trim() || null;
    if (data.recurringRule !== undefined || data.recurring_rule !== undefined) payload.recurring_rule = data.recurringRule?.trim() || data.recurring_rule?.trim() || null;

    if (data.status !== undefined) {
        payload.status = normalizeStatus(data.status);
    }

    if (data.priority !== undefined) {
        payload.priority = data.priority;
    }

    return payload;
}

function notifyActivitiesUpdated() {
    if (typeof window === "undefined") {
        return;
    }

    window.dispatchEvent(
        new CustomEvent(
            "joross:activities-updated"
        )
    );

    window.dispatchEvent(
        new CustomEvent(
            "joross:alerts-updated"
        )
    );
}

function notifyLinkedFarmDataUpdated(activity) {
    if (
        typeof window === "undefined" ||
        !activity?.isAutomatic ||
        activity?.status !== "Completed" ||
        !activity?.sourceModule
    ) {
        return;
    }

    window.dispatchEvent(
        new CustomEvent(
            "joross:farm-data-updated",
            {
                detail: {
                    sourceModule: activity.sourceModule,
                    sourceType: activity.sourceType,
                    sourceRecordId: activity.sourceRecordId,
                },
            }
        )
    );
}

export const activityService = Object.freeze({
    async syncAutomaticActivities() {
        if (automaticSyncRequest) return automaticSyncRequest;
        automaticSyncRequest = httpClient.post("/activities/evaluate", {}).then((response) => {
            inFlightActivityRequests.clear();
            return response?.data ?? response;
        });
        try { return await automaticSyncRequest; }
        finally { automaticSyncRequest = null; }
    },

    async getActivities(
        includeArchived = false,
        {
            dateFrom = "",
            dateTo = "",
        } = {}
    ) {
        const requestKey = createActivityRequestKey(
            includeArchived,
            dateFrom,
            dateTo
        );

        const existingRequest =
            inFlightActivityRequests.get(requestKey);

        if (existingRequest) {
            return existingRequest;
        }

        const requestPromise = (async () => {
            const response = await httpClient.get(
                "/activities",
                {
                    query: {
                        include_archived:
                            includeArchived,
                        date_from: dateFrom,
                        date_to: dateTo,
                    },
                }
            );

            const records = Array.isArray(response)
                ? response
                : response?.data ?? [];

            const normalizedRecords = records.map(
                normalizeActivity
            );

            return includeArchived
                ? normalizedRecords
                : normalizedRecords.filter(
                    (activity) => !activity.isArchived
                );
        })();

        inFlightActivityRequests.set(
            requestKey,
            requestPromise
        );

        try {
            return await requestPromise;
        } finally {
            if (
                inFlightActivityRequests.get(requestKey) ===
                requestPromise
            ) {
                inFlightActivityRequests.delete(
                    requestKey
                );
            }
        }
    },

    async getActivity(activityId) {
        const response = await httpClient.get(
            `/activities/${activityId}`
        );

        return normalizeActivity(
            response?.data ?? response
        );
    },

    getEventResources: loadEventResources,

    async createActivity(data, idempotencyKey = null) {
        const response = await httpClient.post(
            "/activities",
            createActivityPayload(data),
            { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} }
        );

        const activity = normalizeActivity(
            response?.data ?? response
        );

        notifyActivitiesUpdated();
        return activity;
    },

    async updateActivity(activityId, data) {
        const mutationKey = String(activityId);
        const existing = inFlightActivityMutations.get(mutationKey);
        if (existing) return existing;

        const mutation = (async () => {
            const response = await httpClient.put(
                `/activities/${activityId}`,
                createUpdatePayload(data)
            );

            const activity = normalizeActivity(
                response?.data ?? response
            );

            notifyActivitiesUpdated();
            notifyLinkedFarmDataUpdated(activity);
            return activity;
        })();

        inFlightActivityMutations.set(mutationKey, mutation);
        try {
            return await mutation;
        } finally {
            if (inFlightActivityMutations.get(mutationKey) === mutation) {
                inFlightActivityMutations.delete(mutationKey);
            }
        }
    },

    async archiveActivity(activityId) {
        const response = await httpClient.post(
            `/activities/${activityId}/archive`,
            {}
        );

        const activity = normalizeActivity(
            response?.data ?? response
        );

        notifyActivitiesUpdated();
        return activity;
    },

    async restoreActivity(activityId) {
        const response = await httpClient.post(
            `/activities/${activityId}/restore`,
            {}
        );

        const activity = normalizeActivity(
            response?.data ?? response
        );

        notifyActivitiesUpdated();
        return activity;
    },
});
