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
        try {
            const [summary, movements] = await Promise.all([
                inventoryService.getInventorySummary(), inventoryService.getMovementSummary(),
            ]);
            setInventorySummaryData(summary);
            setMovementSummary(movements);
        } catch (error) {
            console.error("Failed to load inventory summary:", error);
            setInventoryError(error?.message || "Unable to load inventory analytics.");
        }
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
        const inStock = inventorySummaryData?.in_stock || 0;
        const lowStock = inventorySummaryData?.low_stock || 0;
        const outOfStock = inventorySummaryData?.out_of_stock || 0;
        const totalValue = inventorySummaryData?.total_value || 0;

        return [
            {
                id: 1,
                title: "Inventory Records",
                value: inventorySummaryData?.total || 0,
                icon: "inventory_2",
                className: "records",
            },
            {
                id: 2,
                title: "In Stock",
                value: inStock,
                icon: "check_circle",
                className: "in-stock",
            },
            {
                id: 3,
                title: "Low Stock",
                value: lowStock,
                icon: "warning",
                className: "low-stock",
            },
            {
                id: 4,
                title: "Out of Stock",
                value: outOfStock,
                icon: "error",
                className: "out-of-stock",
            },
            {
                id: 5,
                title: "Inventory Value",
                value: formatCurrency(totalValue),
                icon: "payments",
                className: "value",
            },
        ];
    }, [inventorySummaryData]);

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
            notify(error?.message || "Unable to load this item's stock history.");
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

            // The POST already returns the authoritative before/after quantity.
            // Apply it locally instead of making a second blocking GET request.
            const applyStockRecord = (item) => {
                if (!item || item.id !== itemId) {
                    return item;
                }

                const existingHistory = item.stockHistory || [];
                const nextHistory = [
                    stockRecord,
                    ...existingHistory.filter((record) => record.id !== stockRecord.id),
                ];

                return {
                    ...item,
                    quantity: stockRecord.newQuantity,
                    supplier:
                        adjustment.type === "Restock" && adjustment.supplier
                            ? adjustment.supplier
                            : item.supplier,
                    stockHistory: nextHistory,
                };
            };

            setInventory((currentInventory) =>
                currentInventory.map(applyStockRecord)
            );

            setSelectedItem((currentItem) => applyStockRecord(currentItem));

            notify("Stock quantity updated successfully.");
            void Promise.all([loadInventory(), loadSummary()]);
            return true;
        } catch (error) {
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
