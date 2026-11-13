import { isRecordEditConflict } from "../../../services/recordEditing.js";
"use client";
import { requestArchive } from "../../../services/archiveService.js";

import { notify } from "../../../context/NotificationContext.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { confirmAction } from "../../../context/NotificationContext.jsx";
import {
    addTimelineEntry,
    logAudit,
} from "../../../services/farmIntelligenceService.js";
import { inventoryService } from "../../../services/inventoryService.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";

function formatCurrency(value) {
    return Number(value || 0).toLocaleString("en-PH", {
        style: "currency",
        currency: "PHP",
        minimumFractionDigits: 2,
    });
}

// Handles Inventory data, filters, modals, and record actions.
export default function useInventoryPage() {
    const [inventory, setInventory] = useState([]);
    const [inventoryLoading, setInventoryLoading] = useState(true);
    const [inventoryError, setInventoryError] = useState("");
    const [movementSummary, setMovementSummary] = useState([]);
    const [inventorySummaryData, setInventorySummaryData] = useState(null);
    const [summaryLoading, setSummaryLoading] = useState(true);
    const [summaryError, setSummaryError] = useState("");
    const [movementError, setMovementError] = useState("");
    const summaryRequestRef = useRef(0);
    const [inventoryTotal, setInventoryTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);
    const requestIdRef = useRef(0);

    // Filters
    const [searchText, setSearchText] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("All");
    const [statusFilter, setStatusFilter] = useState("All");
    const [supplierFilter, setSupplierFilter] = useState("All");
    const [dateFilter, setDateFilter] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");

    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(searchText.trim()), 300);
        return () => window.clearTimeout(timer);
    }, [searchText]);

    // Modal state
    const [inventoryFormOpen, setInventoryFormOpen] = useState(false);
    const [editingItem, setEditingItem] = useState(null);
    const [selectedItem, setSelectedItem] = useState(null);

    const loadInventory = useCallback(async (offset = 0) => {
        const requestId = ++requestIdRef.current;
        const append = offset > 0;
        try {
            if (append) setLoadingMore(true);
            else { setLoadingMore(false); setInventoryLoading(true); }
            setInventoryError("");
            const page = await inventoryService.getInventoryPage({
                offset, limit: 50, search: debouncedSearch,
                category: categoryFilter === "All" ? undefined : categoryFilter,
                supplier: supplierFilter === "All" ? undefined : supplierFilter,
                stock_status: statusFilter === "All" ? undefined : statusFilter,
                date_acquired: dateFilter || undefined,
            });
            if (requestId !== requestIdRef.current) return [];
            setInventory((current) => append
                ? [...current, ...page.items.filter((item) => !current.some((row) => row.id === item.id))]
                : page.items);
            setInventoryTotal(page.total);
            return page.items;
        } catch (error) {
            if (requestId !== requestIdRef.current) return [];
            console.error("Failed to load inventory:", error);
            setInventoryError(
                error?.message || "Unable to load inventory records."
            );
            return [];
        } finally {
            if (requestId === requestIdRef.current) {
                if (append) setLoadingMore(false);
                else setInventoryLoading(false);
            }
        }
    }, [debouncedSearch, categoryFilter, statusFilter, supplierFilter, dateFilter]);

    const loadSummary = useCallback(async () => {
        const requestId = ++summaryRequestRef.current;
        setSummaryLoading(true);
        setSummaryError("");
        setMovementError("");
        const [summary, movements] = await Promise.allSettled([
            inventoryService.getInventorySummary(), inventoryService.getMovementSummary(),
        ]);
        if (requestId !== summaryRequestRef.current) return;
        if (summary.status === "fulfilled") setInventorySummaryData(summary.value);
        else {
            setInventorySummaryData(null);
            setSummaryError(summary.reason?.message || "Inventory totals are unavailable.");
        }
        if (movements.status === "fulfilled") setMovementSummary(movements.value);
        else {
            setMovementSummary([]);
            setMovementError(movements.reason?.message || "Stock movement analytics are unavailable.");
        }
        setSummaryLoading(false);
    }, []);

    useEffect(() => {
        loadInventory();
    }, [loadInventory]);
    useEffect(() => { loadSummary(); }, [loadSummary]);
    useFarmModuleUpdates(["inventory"], () => Promise.all([loadInventory(), loadSummary()]), {
        editing: inventoryFormOpen || Boolean(selectedItem),
    });

    const loadMoreInventory = () => {
        if (!inventoryLoading && !loadingMore && inventory.length < inventoryTotal) {
            void loadInventory(inventory.length);
        }
    };

    const inventoryCategories = useMemo(
        () => [
            ...new Set(
                (inventorySummaryData?.categories || []).filter(Boolean)
            ),
        ],
        [inventorySummaryData]
    );

    const inventorySuppliers = useMemo(
        () => [
            ...new Set(
                (inventorySummaryData?.suppliers || []).filter(Boolean)
            ),
        ],
        [inventorySummaryData]
    );

    const filteredInventory = inventory;

    const inventorySummary = useMemo(() => {
        const count = (value) => summaryLoading ? "…" : summaryError || !inventorySummaryData ? "—" : (value ?? 0);
        const inStock = inventorySummaryData?.in_stock || 0;
        const lowStock = inventorySummaryData?.low_stock || 0;
        const outOfStock = inventorySummaryData?.out_of_stock || 0;
        const totalValue = inventorySummaryData?.total_value || 0;

        return [
            {
                id: 1,
                title: "Inventory Records",
                value: count(inventorySummaryData?.total),
                icon: "inventory_2",
                className: "records",
            },
            {
                id: 2,
                title: "In Stock",
                value: count(inStock),
                icon: "check_circle",
                className: "in-stock",
            },
            {
                id: 3,
                title: "Low Stock",
                value: count(lowStock),
                icon: "warning",
                className: "low-stock",
            },
            {
                id: 4,
                title: "Out of Stock",
                value: count(outOfStock),
                icon: "error",
                className: "out-of-stock",
            },
            {
                id: 5,
                title: "Inventory Value",
                value: summaryLoading || summaryError || !inventorySummaryData ? count(null) : formatCurrency(totalValue),
                icon: "payments",
                className: "value",
            },
        ];
    }, [inventorySummaryData, summaryLoading, summaryError]);

    const clearFilters = () => {
        setSearchText("");
        setCategoryFilter("All");
        setStatusFilter("All");
        setSupplierFilter("All");
        setDateFilter("");
    };

    const openAddInventory = () => {
        setEditingItem(null);
        setInventoryFormOpen(true);
    };

    const openEditInventory = (item) => {
        setEditingItem(item);
        setInventoryFormOpen(true);
    };

    const openViewInventory = async (item) => {
        try {
            setSelectedItem(await inventoryService.getInventoryItem(item.id));
        } catch (error) {
            notify(error?.message || "Unable to load this inventory item.");
        }
    };

    const closeInventoryForm = () => {
        setInventoryFormOpen(false);
        setEditingItem(null);
    };

    const handleSaveInventory = async (formData, { idempotencyKey = null } = {}) => {
        try {
            if (editingItem) {
                const updatedItem = await inventoryService.updateInventory(
                    editingItem.id,
                    formData
                );

                setInventory((currentInventory) =>
                    currentInventory.map((item) =>
                        item.id === editingItem.id ? updatedItem : item
                    )
                );

                setSelectedItem((currentItem) =>
                    currentItem?.id === editingItem.id
                        ? updatedItem
                        : currentItem
                );

                notify("Inventory record updated successfully.");
            } else {
                const newItem = await inventoryService.createInventory(formData, { idempotencyKey });

                setInventory((currentInventory) => [
                    newItem,
                    ...currentInventory,
                ]);

                notify("Inventory record added successfully.");
            }

            closeInventoryForm();
            await Promise.allSettled([loadInventory(), loadSummary()]);
            return true;
        } catch (error) {
            if (isRecordEditConflict(error)) throw error;
            console.error("Failed to save inventory record:", error);
            notify(
                error?.message || "Unable to save inventory record."
            );
            return false;
        }
    };

    const handleAdjustStock = async (itemId, adjustment, idempotencyKey = null) => {
        const adjustedItem = inventory.find((item) => item.id === itemId);

        if (!adjustedItem) {
            return false;
        }

        try {
            const stockRecord = await inventoryService.addStockAdjustment(
                itemId,
                adjustment,
                { idempotencyKey }
            );

            // Fresh saves include the version of their stock update. A historical
            // idempotent replay needs current metadata rather than an old balance.
            let replayItem = null;
            const priorItem = selectedItem?.id === itemId ? selectedItem : adjustedItem;
            const canMerge = Boolean(stockRecord.inventoryEditVersion &&
                priorItem.editVersion === stockRecord.inventoryPreviousEditVersion);
            if (!canMerge) {
                try { replayItem = await inventoryService.getInventoryItem(itemId); }
                catch { /* A missing version requires an explicit reload before an exact correction. */ }
            }
            const applyStockRecord = (item) => {
                if (!item || item.id !== itemId) {
                    return item;
                }

                if (replayItem) return replayItem;

                return {
                    ...priorItem,
                    quantity: stockRecord.inventoryEditVersion ? stockRecord.newQuantity : priorItem.quantity,
                    supplier:
                        adjustment.type === "Restock" && adjustment.supplier
                            ? adjustment.supplier
                            : priorItem.supplier,
                    editVersion: canMerge ? stockRecord.inventoryEditVersion : undefined,
                    stockHistory: [],
                };
            };

            setInventory((currentInventory) =>
                currentInventory.map(applyStockRecord)
            );

            setSelectedItem((currentItem) => applyStockRecord(currentItem));

            notify(!canMerge && !replayItem
                ? "Stock submission confirmed. Reload item details to verify the current balance."
                : "Stock quantity updated successfully.");
            void Promise.all([loadInventory(), loadSummary()]);
            return applyStockRecord(selectedItem?.id === itemId ? selectedItem : adjustedItem);
        } catch (error) {
            if (isRecordEditConflict(error)) throw error;
            console.error("Failed to adjust inventory stock:", error);
            notify(
                error?.message || "Unable to update stock quantity."
            );
            return false;
        }
    };

    const archiveInventoryItem = async (itemId) => {
        const item = inventory.find((record) => record.id === itemId);

        if (!item) {
            return;
        }

        const confirmed = await requestArchive("Inventory", itemId, item.name);

        if (!confirmed) {
            return;
        }

        try {

            setInventory((currentInventory) =>
                currentInventory.filter((record) => record.id !== itemId)
            );

            if (selectedItem?.id === itemId) {
                setSelectedItem(null);
            }
            await Promise.all([loadInventory(), loadSummary()]);

            logAudit({
                action: "Archived inventory record",
                module: "Inventory",
                recordName: item.name,
                entityId: item.itemCode,
                details: item.location,
            });

            addTimelineEntry({
                module: "Inventory",
                recordName: item.name,
                entityId: item.itemCode,
                title: "Inventory item archived",
                details: `${item.category} record archived.`,
                icon: "archive",
            });

            notify(`${item.name} was archived successfully.`);
        } catch (error) {
            console.error("Failed to archive inventory record:", error);
            notify(
                error?.message || "Unable to archive inventory record."
            );
        }
    };


    return {
        inventory,
        inventoryLoading,
        inventoryError,
        inventorySummary,
        inventorySummaryData,
        summaryLoading,
        summaryError,
        movementError,
        loadSummary,
        inventoryTotal,
        loadingMore,
        loadMoreInventory,
        movementSummary,
        inventoryCategories,
        inventorySuppliers,
        filteredInventory,

        searchText,
        setSearchText,
        categoryFilter,
        setCategoryFilter,
        statusFilter,
        setStatusFilter,
        supplierFilter,
        setSupplierFilter,
        dateFilter,
        setDateFilter,
        clearFilters,

        inventoryFormOpen,
        editingItem,
        selectedItem,
        setSelectedItem,
        openViewInventory,
        openAddInventory,
        openEditInventory,
        closeInventoryForm,
        handleSaveInventory,
        handleAdjustStock,
        archiveInventoryItem,
    };
}
