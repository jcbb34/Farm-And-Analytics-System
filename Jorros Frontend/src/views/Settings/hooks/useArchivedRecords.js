import { notify } from "../../../context/NotificationContext.jsx";
import {
    useEffect,
    useMemo,
    useState,
} from "react";

import { cropService } from "../../../services/cropService.js";
import { livestockService } from "../../../services/livestockService.js";
import { inventoryService } from "../../../services/inventoryService.js";
import { reportService } from "../../../services/reportService.js";
import { confirmAction } from "../../../context/NotificationContext.jsx";

// Keeps archived records and archive actions in one place.
export function useArchivedRecords() {
    const [
        archivedRecords,
        setArchivedRecords,
    ] = useState([]);

    const [
        search,
        setSearch,
    ] = useState("");

    const [
        moduleFilter,
        setModuleFilter,
    ] = useState("All");

    useEffect(() => {
        let cancelled = false;

        const loadArchivedRecords = async () => {
            const results =
                await Promise.allSettled([
                    cropService.getCrops(true),
                    livestockService.getLivestock(true),
                    inventoryService.getInventory(true),
                    reportService.getReports(true),
                ]);

            if (cancelled) {
                return;
            }

            const [
                cropsResult,
                livestockResult,
                inventoryResult,
                reportsResult,
            ] = results;

            const records = [];

            if (cropsResult.status === "fulfilled") {
                records.push(
                    ...cropsResult.value
                        .filter(
                            (crop) =>
                                crop.isArchived
                        )
                        .map((crop) => ({
                            id: `crop-${crop.id}`,
                            sourceId: crop.id,
                            recordName: crop.cropCode
                                ? `${crop.name} (${crop.cropCode})`
                                : crop.name,
                            module: "Crop",
                            reason: "Crop record archived",
                            archivedDate:
                                crop.updatedAt ||
                                crop.createdAt ||
                                "",
                            archivedBy: "Not recorded",
                            apiBacked: true,
                        }))
                );
            } else {
                console.error(
                    "Failed to load archived crop records:",
                    cropsResult.reason
                );
            }

            if (livestockResult.status === "fulfilled") {
                records.push(
                    ...livestockResult.value
                        .filter(
                            (record) =>
                                record.isArchived
                        )
                        .map((record) => ({
                            id: `livestock-${record.id}`,
                            sourceId: record.id,
                            recordName: record.animalId
                                ? `${record.recordName} (${record.animalId})`
                                : record.recordName,
                            module: "Livestock",
                            reason: "Livestock record archived",
                            archivedDate:
                                record.updatedAt ||
                                record.createdAt ||
                                "",
                            archivedBy: "Not recorded",
                            apiBacked: true,
                        }))
                );
            } else {
                console.error(
                    "Failed to load archived livestock records:",
                    livestockResult.reason
                );
            }

            if (inventoryResult.status === "fulfilled") {
                records.push(
                    ...inventoryResult.value
                        .filter(
                            (record) =>
                                record.isArchived
                        )
                        .map((record) => ({
                            id: `inventory-${record.id}`,
                            sourceId: record.id,
                            recordName: record.itemCode
                                ? `${record.name} (${record.itemCode})`
                                : record.name,
                            module: "Inventory",
                            reason: "Inventory item archived",
                            archivedDate:
                                record.updatedAt ||
                                record.createdAt ||
                                "",
                            archivedBy: "Not recorded",
                            apiBacked: true,
                        }))
                );
            } else {
                console.error(
                    "Failed to load archived inventory records:",
                    inventoryResult.reason
                );
            }

            if (reportsResult.status === "fulfilled") {
                records.push(
                    ...reportsResult.value
                        .filter(
                            (record) =>
                                record.status ===
                                "Archived"
                        )
                        .map((record) => ({
                            id: `report-${record.id}`,
                            sourceId: record.id,
                            recordName: record.reportCode
                                ? `${record.title} (${record.reportCode})`
                                : record.title,
                            module: "Report",
                            reason: "Report archived",
                            archivedDate:
                                record.updatedAt ||
                                record.createdAt ||
                                record.generatedDate ||
                                "",
                            archivedBy:
                                record.preparedBy ||
                                "Not recorded",
                            apiBacked: true,
                        }))
                );
            } else {
                console.error(
                    "Failed to load archived report records:",
                    reportsResult.reason
                );
            }

            setArchivedRecords(records);
        };

        loadArchivedRecords();

        return () => {
            cancelled = true;
        };
    }, []);

    const filteredRecords = useMemo(() => {
        const normalizedSearch =
            search.trim().toLowerCase();

        return archivedRecords.filter(
            (record) => {
                const matchesSearch =
                    !normalizedSearch ||
                    record.recordName
                        .toLowerCase()
                        .includes(normalizedSearch) ||
                    record.reason
                        .toLowerCase()
                        .includes(normalizedSearch) ||
                    record.archivedBy
                        .toLowerCase()
                        .includes(normalizedSearch);

                const matchesModule =
                    moduleFilter === "All" ||
                    record.module === moduleFilter;

                return (
                    matchesSearch &&
                    matchesModule
                );
            }
        );
    }, [
        archivedRecords,
        search,
        moduleFilter,
    ]);

    const restoreRecord = async (record) => {
        const confirmed =
            await confirmAction({
                title: "Restore Archived Record",
                message: `Restore "${record.recordName}"?`,
                type: "info",
                confirmText: "Restore",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            if (record.apiBacked) {
                if (record.module === "Crop") {
                    await cropService.restoreCrop(
                        record.sourceId
                    );
                } else if (
                    record.module === "Livestock"
                ) {
                    await livestockService.restoreLivestock(
                        record.sourceId
                    );
                } else if (
                    record.module === "Inventory"
                ) {
                    await inventoryService.restoreInventory(
                        record.sourceId
                    );
                } else if (
                    record.module === "Report"
                ) {
                    await reportService.restoreReport(
                        record.sourceId
                    );
                }
            }

            setArchivedRecords(
                (currentRecords) =>
                    currentRecords.filter(
                        (item) =>
                            item.id !== record.id
                    )
            );

            notify(
                `${record.recordName} was restored successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to restore archived record:",
                error
            );

            notify(
                error?.message ||
                    `Unable to restore ${record.recordName}.`
            );
        }
    };

    const deleteRecord = async (record) => {
        const confirmed =
            await confirmAction({
                title: "Permanently Delete Record",
                message:
                    `Permanently remove "${record.recordName}" from archived records? This cannot be undone.`,
                type: "error",
                confirmText: "Delete Permanently",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            if (record.apiBacked) {
                if (record.module === "Crop") {
                    await cropService.deleteCropPermanently(
                        record.sourceId
                    );
                } else if (record.module === "Livestock") {
                    await livestockService.deleteLivestockPermanently(
                        record.sourceId
                    );
                } else if (record.module === "Inventory") {
                    await inventoryService.deleteInventoryPermanently(
                        record.sourceId
                    );
                } else if (record.module === "Report") {
                    await reportService.deleteReportPermanently(
                        record.sourceId
                    );
                }
            }

            setArchivedRecords(
                (currentRecords) =>
                    currentRecords.filter(
                        (item) =>
                            item.id !== record.id
                    )
            );

            notify(
                `${record.recordName} was permanently deleted.`
            );
        } catch (error) {
            console.error(
                "Failed to permanently delete archived record:",
                error
            );

            notify(
                error?.message ||
                    `Unable to permanently delete ${record.recordName}.`
            );
        }
    };

    const resetFilters = () => {
        setSearch("");
        setModuleFilter("All");
    };

    return {
        archivedRecords,
        filteredRecords,
        search,
        moduleFilter,
        setSearch,
        setModuleFilter,
        restoreRecord,
        deleteRecord,
        resetFilters,
    };
}
