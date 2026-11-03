import { httpClient } from "./httpClient.js";

function normalizeUsage(record = {}) {
    return {
        id: record.id,
        module: record.module ?? "",
        targetId: record.targetId ?? record.target_id ?? null,
        targetName: record.targetName ?? record.target_name ?? "",
        inventoryItemId:
            record.inventoryItemId ?? record.inventory_item_id ?? null,
        inventoryItemCode:
            record.inventoryItemCode ?? record.inventory_item_code ?? "",
        inventoryItemName:
            record.inventoryItemName ?? record.inventory_item_name ?? "",
        inventoryCategory:
            record.inventoryCategory ?? record.inventory_category ?? "",
        batchNumber: record.batchNumber ?? record.batch_number ?? "",
        basisValue: record.basisValue ?? record.basis_value ?? null,
        basisUnit: record.basisUnit ?? record.basis_unit ?? "",
        usageType: record.usageType ?? record.usage_type ?? "",
        quantity: Number(record.quantity ?? 0),
        unit: record.unit ?? "",
        usageDate: record.usageDate ?? record.usage_date ?? "",
        notes: record.notes ?? "",
        isVoided: Boolean(record.isVoided ?? record.is_voided ?? false),
        voidReason: record.voidReason ?? record.void_reason ?? "",
        availableQuantity: Number(
            record.availableQuantity ?? record.available_quantity ?? 0
        ),
        efficiencyValue:
            record.efficiencyValue ?? record.efficiency_value ?? null,
        efficiencyLabel:
            record.efficiencyLabel ?? record.efficiency_label ?? "",
        recordedByUserId:
            record.recordedByUserId ?? record.recorded_by_user_id ?? null,
        createdAt: record.createdAt ?? record.created_at ?? null,
        updatedAt: record.updatedAt ?? record.updated_at ?? null,
    };
}

function normalizeSummary(record = {}) {
    return {
        startDate: record.startDate ?? record.start_date ?? "",
        endDate: record.endDate ?? record.end_date ?? "",
        totalRecords: Number(record.totalRecords ?? record.total_records ?? 0),
        totals: (record.totals ?? []).map((row) => ({
            module: row.module ?? "",
            usageType: row.usageType ?? row.usage_type ?? "",
            unit: row.unit ?? "",
            quantity: Number(row.quantity ?? 0),
        })),
        topItems: (record.topItems ?? record.top_items ?? []).map((row) => ({
            inventoryItemId:
                row.inventoryItemId ?? row.inventory_item_id ?? null,
            itemName: row.itemName ?? row.item_name ?? "",
            unit: row.unit ?? "",
            quantity: Number(row.quantity ?? 0),
        })),
        lowStockItems: Number(record.lowStockItems ?? record.low_stock_items ?? 0),
        expiringItems: Number(record.expiringItems ?? record.expiring_items ?? 0),
    };
}

export const resourceUsageService = Object.freeze({
    async getUsages({
        module,
        targetId,
        inventoryItemId,
        includeVoided = false,
        startDate,
        endDate,
    } = {}) {
        const response = await httpClient.get("/resource-usages", {
            query: {
                module,
                target_id: targetId,
                inventory_item_id: inventoryItemId,
                include_voided: includeVoided,
                start_date: startDate,
                end_date: endDate,
            },
        });
        return (Array.isArray(response) ? response : response?.data ?? []).map(
            normalizeUsage
        );
    },

    async createUsage(data, { idempotencyKey = null } = {}) {
        const response = await httpClient.post("/resource-usages", {
            module: data.module,
            target_id: Number(data.targetId),
            inventory_item_id: Number(data.inventoryItemId),
            usage_type: data.usageType,
            quantity: Number(data.quantity),
            usage_date: data.usageDate,
            notes: data.notes?.trim() || null,
        }, { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} });
        return normalizeUsage(response?.data ?? response);
    },

    async updateUsage(usageId, data) {
        const response = await httpClient.put(`/resource-usages/${usageId}`, {
            inventory_item_id: Number(data.inventoryItemId),
            usage_type: data.usageType,
            quantity: Number(data.quantity),
            usage_date: data.usageDate,
            notes: data.notes?.trim() || null,
        });
        return normalizeUsage(response?.data ?? response);
    },

    async deleteUsage(usageId, reason) {
        const response = await httpClient.delete(`/resource-usages/${usageId}`, {
            query: { reason },
        });
        return normalizeUsage(response?.data ?? response);
    },

    async getSummary(days = 30) {
        const response = await httpClient.get(
            "/resource-usages/analytics/summary",
            { query: { days } }
        );
        return normalizeSummary(response?.data ?? response);
    },

    async exportCsv({ startDate, endDate } = {}) {
        return httpClient.get("/resource-usages/export/csv", {
            query: {
                start_date: startDate,
                end_date: endDate,
            },
        });
    },
});
