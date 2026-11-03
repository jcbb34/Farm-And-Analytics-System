import { httpClient } from "./httpClient.js";

function notifyInventoryChanged() {
    if (typeof window === "undefined") {
        return;
    }

    window.dispatchEvent(
        new CustomEvent("joross:farm-data-updated", {
            detail: {
                sourceModule: "Inventory",
            },
        })
    );

    window.dispatchEvent(
        new CustomEvent("joross:activities-updated")
    );

    window.dispatchEvent(
        new CustomEvent("joross:alerts-updated")
    );
}

function normalizeStockRecord(record = {}) {
    return {
        id: record.id,

        inventoryItemId:
            record.inventoryItemId ??
            record.inventory_item_id,

        resourceUsageId:
            record.resourceUsageId ??
            record.resource_usage_id ??
            null,

        type:
            record.type ??
            record.adjustmentType ??
            record.adjustment_type ??
            "",

        quantity: Number(record.quantity ?? 0),

        previousQuantity: Number(
            record.previousQuantity ??
                record.previous_quantity ??
                0
        ),

        newQuantity: Number(
            record.newQuantity ??
                record.new_quantity ??
                0
        ),

        date:
            record.date ??
            record.adjustmentDate ??
            record.adjustment_date ??
            "",

        reason: record.reason ?? "",

        reference:
            record.reference ?? "",

        supplier:
            record.supplier ?? "",

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

function normalizeInventoryItem(record = {}) {
    const stockHistory =
        record.stockHistory ??
        record.stock_history ??
        [];

    return {
        id: record.id,

        itemCode:
            record.itemCode ??
            record.item_code ??
            "",

        name: record.name ?? "",
        category: record.category ?? "",
        batchNumber:
            record.batchNumber ??
            record.batch_number ??
            "",
        quantity: Number(record.quantity ?? 0),
        unit: record.unit ?? "",

        reorderLevel: Number(
            record.reorderLevel ??
                record.reorder_level ??
                0
        ),

        cost: Number(record.cost ?? 0),
        price: Number(record.price ?? 0),
        isSaleable: Boolean(record.isSaleable ?? record.is_saleable ?? false),
        supplier: record.supplier ?? "",

        dateAcquired:
            record.dateAcquired ??
            record.date_acquired ??
            "",

        expirationDate:
            record.expirationDate ??
            record.expiration_date ??
            "",

        location: record.location ?? "",
        description: record.description ?? "",
        notes: record.notes ?? "",

        stockHistory: stockHistory.map(
            normalizeStockRecord
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

function createInventoryPayload(data = {}) {
    return {
        name: data.name?.trim() ?? "",
        category: data.category?.trim() ?? "",
        batch_number: data.batchNumber?.trim() || null,
        quantity: Number(data.quantity ?? 0),
        unit: data.unit?.trim() ?? "",
        reorder_level: Number(
            data.reorderLevel ?? 0
        ),
        cost: Number(data.cost ?? 0),
        price: Number(data.price ?? 0),
        is_saleable: Boolean(data.isSaleable),
        supplier: data.supplier?.trim() ?? "",
        date_acquired: data.dateAcquired,
        expiration_date:
            data.expirationDate || null,
        location: data.location?.trim() ?? "",
        description:
            data.description?.trim() || null,
        notes: data.notes?.trim() || null,
    };
}

function createInventoryUpdatePayload(data = {}) {
    const payload = {};

    if (data.name !== undefined) {
        payload.name = data.name.trim();
    }

    if (data.category !== undefined) {
        payload.category = data.category.trim();
    }

    if (data.batchNumber !== undefined) {
        payload.batch_number = data.batchNumber?.trim() || null;
    }

    if (data.unit !== undefined) {
        payload.unit = data.unit.trim();
    }

    if (data.reorderLevel !== undefined) {
        payload.reorder_level = Number(
            data.reorderLevel
        );
    }

    if (data.cost !== undefined) {
        payload.cost = Number(data.cost);
    }

    if (data.price !== undefined) {
        payload.price = Number(data.price);
    }

    if (data.isSaleable !== undefined) {
        payload.is_saleable = Boolean(data.isSaleable);
    }

    if (data.supplier !== undefined) {
        payload.supplier = data.supplier.trim();
    }

    if (data.dateAcquired !== undefined) {
        payload.date_acquired = data.dateAcquired;
    }

    if (data.expirationDate !== undefined) {
        payload.expiration_date =
            data.expirationDate || null;
    }

    if (data.location !== undefined) {
        payload.location = data.location.trim();
    }

    if (data.description !== undefined) {
        payload.description =
            data.description?.trim() || null;
    }

    if (data.notes !== undefined) {
        payload.notes = data.notes?.trim() || null;
    }

    return payload;
}

export const inventoryService = Object.freeze({
    async getInventoryPage(options = {}) {
        const response = await httpClient.get("/inventory/page", { query: options });
        return { ...response, items: (response.items || []).map(normalizeInventoryItem) };
    },
    async getInventorySummary() {
        const response = await httpClient.get("/inventory/summary");
        return {
            ...response,
            lowStockItems: (response.low_stock_items || []).map(normalizeInventoryItem),
            expirationItems: (response.expiration_items || []).map(normalizeInventoryItem),
        };
    },
    getMovementSummary() {
        return httpClient.get("/inventory/movements/summary");
    },
    async getInventory(
        includeArchived = false,
        includeDetails = false
    ) {
        const response = await httpClient.get(
            includeDetails
                ? "/inventory/details"
                : "/inventory",
            {
                query: {
                    include_archived:
                        includeArchived,
                },
            }
        );

        const records = Array.isArray(response)
            ? response
            : response?.data ?? [];

        return records.map(
            normalizeInventoryItem
        );
    },

    async getInventoryItem(inventoryId) {
        const response = await httpClient.get(
            `/inventory/${inventoryId}`
        );

        return normalizeInventoryItem(
            response?.data ?? response
        );
    },

    async createInventory(data, { idempotencyKey = null } = {}) {
        const response = await httpClient.post(
            "/inventory",
            createInventoryPayload(data),
            { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} }
        );

        const item = normalizeInventoryItem(
            response?.data ?? response
        );
        notifyInventoryChanged();
        return item;
    },

    async updateInventory(inventoryId, data) {
        const response = await httpClient.put(
            `/inventory/${inventoryId}`,
            createInventoryUpdatePayload(data)
        );

        const item = normalizeInventoryItem(
            response?.data ?? response
        );

        notifyInventoryChanged();
        return item;
    },

    async archiveInventory(inventoryId) {
        const response = await httpClient.post(
            `/inventory/${inventoryId}/archive`,
            {}
        );

        return normalizeInventoryItem(
            response?.data ?? response
        );
    },

    async restoreInventory(inventoryId) {
        const response = await httpClient.post(
            `/inventory/${inventoryId}/restore`,
            {}
        );

        return normalizeInventoryItem(
            response?.data ?? response
        );
    },

    async deleteInventoryPermanently(inventoryId) {
        await httpClient.delete(
            `/inventory/${inventoryId}/permanent`
        );

        return true;
    },

    async addStockAdjustment(
        inventoryId,
        adjustment,
        { idempotencyKey = null } = {}
    ) {
        const response = await httpClient.post(
            `/inventory/${inventoryId}/stock-adjustments`,
            {
                adjustment_type:
                    adjustment.type,
                quantity: Number(
                    adjustment.quantity
                ),
                adjustment_date:
                    adjustment.date,
                reason:
                    adjustment.reason?.trim() ??
                    "",
                reference:
                    adjustment.reference?.trim() ||
                    null,
                supplier:
                    adjustment.supplier?.trim() ||
                    null,
            },
            {
                headers: idempotencyKey
                    ? { "Idempotency-Key": idempotencyKey }
                    : {},
            }
        );

        const record = normalizeStockRecord(
            response?.data ?? response
        );

        notifyInventoryChanged();
        return record;
    },
});
