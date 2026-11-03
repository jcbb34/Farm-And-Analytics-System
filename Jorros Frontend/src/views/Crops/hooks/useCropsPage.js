"use client";
import { requestArchive } from "../../../services/archiveService.js";

import { notify } from "../../../context/NotificationContext.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { confirmAction } from "../../../context/NotificationContext.jsx";
import { useAuth } from "../../../context/AuthContext.jsx";
import { cropService } from "../../../services/cropService.js";
import { workforceService } from "../../../services/workforceService.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";
import { CROP_LIFECYCLE_FILTERS, matchesCropLifecycleFilter, sortCropsByHarvestPriority } from "../cropLifecycle.js";
import {
    addTimelineEntry,
    logAudit,
} from "../../../services/farmIntelligenceService.js";
import {
    clearStableIdempotencyKey,
    stableIdempotencyKey,
} from "../../../services/idempotencyKey.js";

// Handles Crops page data, filters, modals, and record actions.
export default function useCropsPage() {
    const { isAdministrator, hasPermission } = useAuth();

    const canUpdateCrops =
        isAdministrator || hasPermission?.("crops:update");

    const canFullEditCrops =
        isAdministrator || hasPermission?.("crops:full-edit");

    const [crops, setCrops] = useState([]);
    const [yieldRecords, setYieldRecords] = useState([]);
    const [cropsLoading, setCropsLoading] = useState(true);
    const [cropsError, setCropsError] = useState("");
    const [employees, setEmployees] = useState([]);

    // Filters
    const [searchText, setSearchText] = useState("");
    const [cropType, setCropType] = useState("All");
    const [statusFilter, setStatusFilter] = useState("Active Crops");
    const [fieldFilter, setFieldFilter] = useState("All");
    const [dateFilter, setDateFilter] = useState("");

    // Modal state
    const [addCropOpen, setAddCropOpen] = useState(false);
    const [addYieldOpen, setAddYieldOpen] = useState(false);
    const [selectedCrop, setSelectedCrop] = useState(null);
    const [editCrop, setEditCrop] = useState(null);
    const [reopenCropTarget, setReopenCropTarget] = useState(null);
    const [harvestCropId, setHarvestCropId] = useState(null);
    const cropCreateRequestRef = useRef(null);
    const cropHarvestRequestRef = useRef(null);
    const cropHarvestInFlightRef = useRef(false);

    const loadCrops = useCallback(async () => {
        try {
            setCropsLoading(true);
            setCropsError("");

            const cropList = await cropService.getCrops(true, true);
            setCrops(cropList);

            const allYieldRecords = cropList.flatMap((crop) =>
                (crop.yieldRecords ?? []).map((record) => ({
                    ...record,
                    cropName: crop.name,
                    field: crop.field,
                    area: crop.area,
                }))
            );

            setYieldRecords(allYieldRecords);
            return cropList;
        } catch (error) {
            console.error("Failed to load crops:", error);
            setCropsError(error?.message || "Unable to load crop records.");
            return [];
        } finally {
            setCropsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadCrops();
    }, [loadCrops]);
    useFarmModuleUpdates(["crops", "production_sales"], loadCrops, {
        editing: addCropOpen || addYieldOpen || Boolean(editCrop) || Boolean(reopenCropTarget),
    });

    useEffect(() => {
        if (!canUpdateCrops) return;
        workforceService.getEmployees(false)
            .then((rows) => setEmployees(Array.isArray(rows) ? rows.filter((row) => !row.is_archived && row.employment_status !== "Inactive") : []))
            .catch(() => setEmployees([]));
    }, [canUpdateCrops]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const requestedStatus = params.get("status");
        if (CROP_LIFECYCLE_FILTERS.includes(requestedStatus)) {
            setStatusFilter(requestedStatus);
        }
        const requestedCropId = Number(params.get("cropId") || 0);
        if (requestedCropId) {
            const found = crops.find((crop) => crop.id === requestedCropId);
            if (found) setSelectedCrop(found);
        }
        if (params.get("addYield") === "1" && canUpdateCrops) {
            if (requestedCropId) setHarvestCropId(requestedCropId);
            setAddYieldOpen(true);
            params.delete("addYield");
            const next = params.toString();
            window.history.replaceState({}, "", `${window.location.pathname}${next ? `?${next}` : ""}`);
        }
    }, [canUpdateCrops, crops]);

    const cropSummary = useMemo(() => {
        const activeCrops = crops.filter(
            (crop) => crop.status !== "Harvested" && crop.status !== "Failed"
        ).length;

        const harvestedCrops = crops.filter(
            (crop) => crop.status === "Harvested"
        ).length;

        const cropAlerts = crops.filter(
            (crop) => crop.activePestDisease !== null
        ).length;

        return [
            {
                id: 1,
                title: "Total Crops",
                value: crops.length,
                icon: "potted_plant",
                className: "total",
            },
            {
                id: 2,
                title: "Active Crops",
                value: activeCrops,
                icon: "eco",
                className: "active",
            },
            {
                id: 3,
                title: "Harvested",
                value: harvestedCrops,
                icon: "agriculture",
                className: "harvested",
            },
            {
                id: 4,
                title: "Crop Alerts",
                value: cropAlerts,
                icon: "warning",
                className: "alerts",
            },
        ];
    }, [crops]);

    const cropTypes = useMemo(
        () => [...new Set(crops.map((crop) => crop.name).filter(Boolean))],
        [crops]
    );

    const cropFields = useMemo(
        () => [...new Set(crops.map((crop) => crop.field).filter(Boolean))],
        [crops]
    );

    const harvestEligibleCrops = useMemo(
        () => crops.filter((crop) => ["Ready for Harvest", "Harvesting"].includes(crop.status) && !crop.isArchived && !crop.pendingHarvestTaskId),
        [crops]
    );

    const readyForHarvestCount = useMemo(
        () => crops.filter((crop) => crop.status === "Ready for Harvest" && !crop.isArchived).length,
        [crops]
    );

    const filteredCrops = useMemo(() => {
        const normalizedSearch = searchText.trim().toLowerCase();

        const filtered = crops.filter((crop) => {
            const name = String(crop.name || "").toLowerCase();
            const variety = String(crop.variety || "").toLowerCase();
            const field = String(crop.field || "").toLowerCase();

            const matchesSearch =
                !normalizedSearch ||
                name.includes(normalizedSearch) ||
                variety.includes(normalizedSearch) ||
                field.includes(normalizedSearch);

            const matchesType = cropType === "All" || crop.name === cropType;
            const matchesStatus = matchesCropLifecycleFilter(crop, statusFilter);
            const matchesField =
                fieldFilter === "All" || crop.field === fieldFilter;
            const matchesDate =
                !dateFilter || crop.plantingDate === dateFilter;

            return (
                matchesSearch &&
                matchesType &&
                matchesStatus &&
                matchesField &&
                matchesDate
            );
        });
        return sortCropsByHarvestPriority(filtered);
    }, [
        crops,
        searchText,
        cropType,
        statusFilter,
        fieldFilter,
        dateFilter,
    ]);

    const clearFilters = () => {
        setSearchText("");
        setCropType("All");
        setStatusFilter("Active Crops");
        setFieldFilter("All");
        setDateFilter("");
    };

    const handleAddCrop = async (newCropData) => {
        const idempotencyKey = stableIdempotencyKey(
            cropCreateRequestRef,
            newCropData,
            "crop-create"
        );
        try {
            await cropService.createCrop(
                newCropData,
                { idempotencyKey }
            );
            clearStableIdempotencyKey(cropCreateRequestRef);
            await loadCrops();
            setAddCropOpen(false);



            notify("Crop record added successfully.");
        } catch (error) {
            console.error("Failed to add crop:", error);
            notify(error?.message || "Unable to add crop record.");
        }
    };

    const handleEditCrop = async (updatedCropData) => {
        if (!editCrop) return;

        try {
            const updatedCrop = await cropService.updateCrop(
                editCrop.id,
                updatedCropData
            );

            const refreshedCrops = await loadCrops();
            const refreshedCrop =
                refreshedCrops.find((crop) => crop.id === editCrop.id) ??
                updatedCrop;

            if (selectedCrop?.id === editCrop.id) {
                setSelectedCrop(refreshedCrop);
            }



            setEditCrop(null);
            notify("Crop information updated successfully.");
        } catch (error) {
            console.error("Failed to edit crop:", error);
            notify(error?.message || "Unable to update crop information.");
        }
    };

    const handleAddYield = async (yieldData) => {
        if (cropHarvestInFlightRef.current) {
            return;
        }
        const selectedCropRecord = crops.find(
            (crop) => crop.id === yieldData.cropId
        );

        if (!selectedCropRecord) {
            notify("Selected crop record was not found.");
            return;
        }

        if (!["Ready for Harvest", "Harvesting"].includes(selectedCropRecord.status)) {
            notify("Only crops that are Ready for Harvest or Harvesting can receive a yield record.");
            return;
        }

        const idempotencyKey = stableIdempotencyKey(cropHarvestRequestRef, yieldData, `crop-harvest-${yieldData.cropId}`);
        cropHarvestInFlightRef.current = true;
        try {
            await cropService.addYieldRecord(yieldData.cropId, yieldData, { idempotencyKey });
            clearStableIdempotencyKey(cropHarvestRequestRef);
            const refreshedCrops = await loadCrops();

            if (selectedCrop?.id === yieldData.cropId) {
                const refreshedCrop = refreshedCrops.find(
                    (crop) => crop.id === yieldData.cropId
                );

                if (refreshedCrop) setSelectedCrop(refreshedCrop);
            }

            logAudit({
                action: "Added crop yield record",
                module: "Crop",
                recordName: selectedCropRecord.name,
                entityId: selectedCropRecord.id,
                details: `${yieldData.quantityKg} kg • ${yieldData.harvestType} • ${yieldData.quality}`,
            });

            addTimelineEntry({
                module: "Crop",
                recordName: selectedCropRecord.name,
                entityId: selectedCropRecord.id,
                title: "Yield recorded",
                details: `${yieldData.quantityKg} kg • ${yieldData.harvestType}`,
                icon: "agriculture",
                timestamp: new Date(
                    `${yieldData.harvestDate}T12:00:00`
                ).toISOString(),
            });

            setAddYieldOpen(false);
            setHarvestCropId(null);
            notify(yieldData.harvestType === "Final Harvest" ? "Final harvest recorded. The crop cycle is now completed." : "Partial harvest recorded successfully.");
        } catch (error) {
            console.error("Failed to add crop yield:", error);
            notify(error?.message || "Unable to add yield record.");
        } finally {
            cropHarvestInFlightRef.current = false;
        }
    };

    const openHarvestForCrop = (crop) => {
        setHarvestCropId(crop?.id ?? null);
        setAddYieldOpen(true);
    };


    const openPendingHarvestTask = useCallback((crop) => {
        if (!crop?.pendingHarvestTaskId) return;
        const returnTo = `${window.location.pathname}${window.location.search || ""}`;
        const params = new URLSearchParams({
            tab: "tasks",
            taskId: String(crop.pendingHarvestTaskId),
            from: "crops",
            returnTo,
        });
        window.location.assign(`/task-management?${params.toString()}`);
    }, []);

    const handleConfirmReady = async (crop) => {
        try {
            await cropService.confirmReady(crop.id);
            await loadCrops();
            notify(`${crop.name} is now confirmed Ready for Harvest.`);
        } catch (error) {
            notify(error?.message || "Unable to confirm crop readiness.");
        }
    };

    const handleReopenCrop = async ({ reason, newStatus }) => {
        if (!reopenCropTarget) return;
        const reopened = await cropService.reopenCrop(reopenCropTarget.id, reason, newStatus);
        if (reopened.status !== newStatus) {
            throw new Error("The crop still appears Fully Harvested. Please retry or check the crop history.");
        }
        setCrops((current) => current.map((crop) => crop.id === reopened.id ? reopened : crop));
        const refreshedCrops = await loadCrops();
        const refreshed = refreshedCrops.find((crop) => crop.id === reopenCropTarget.id);
        if (refreshed && refreshed.status !== newStatus) {
            throw new Error("The crop list still shows Fully Harvested after reopening. Please retry.");
        }
        if (selectedCrop?.id === reopenCropTarget.id) {
            setSelectedCrop(refreshed || reopened);
        }
        setReopenCropTarget(null);
        notify("Crop cycle reopened. Existing harvest and report history were kept.");
    };

    const handleArchiveCrop = async (cropId) => {
        const cropToArchive = crops.find((crop) => crop.id === cropId);
        if (!cropToArchive) return;

        const confirmed = await requestArchive("Crop", cropId, cropToArchive.name);

        if (!confirmed) return;

        try {
            await loadCrops();

            if (selectedCrop?.id === cropId) {
                setSelectedCrop(null);
            }



            notify(`${cropToArchive.name} was archived successfully.`);
        } catch (error) {
            console.error("Failed to archive crop:", error);
            notify(error?.message || "Unable to archive crop record.");
        }
    };

    const handleSavePestDisease = async (cropId, pestDisease) => {
        const pestCrop = crops.find((crop) => crop.id === cropId);

        if (!pestCrop) {
            notify("Selected crop record was not found.");
            return;
        }

        try {
            await cropService.addPestDisease(cropId, pestDisease);
            const updatedCrop = await cropService.getCrop(cropId);

            setCrops((currentCrops) =>
                currentCrops.map((crop) =>
                    crop.id === cropId ? updatedCrop : crop
                )
            );
            setSelectedCrop(updatedCrop);

            logAudit({
                action: "Saved pest or disease record",
                module: "Crop",
                recordName: pestCrop.name,
                entityId: pestCrop.id,
                details:
                    pestDisease?.type || "Pest / disease observation",
            });

            addTimelineEntry({
                module: "Crop",
                recordName: pestCrop.name,
                entityId: pestCrop.id,
                title: "Pest / disease observation",
                details: `${pestDisease?.type || "Observation"}${
                    pestDisease?.severity ? ` • ${pestDisease.severity}` : ""
                }`,
                icon: "bug_report",
            });

            notify("Pest or disease record saved successfully.");
        } catch (error) {
            console.error("Failed to save pest or disease record:", error);
            notify(
                error?.message || "Unable to save pest or disease record."
            );
        }
    };

    const handleSaveGrowthCheck = async (cropId, growthData) => {
        const growthCrop = crops.find((crop) => crop.id === cropId);
        if (!growthCrop) return;

        try {
            await cropService.addGrowthRecord(cropId, growthData);
            const refreshedCrops = await loadCrops();
            const refreshedCrop = refreshedCrops.find((crop) => crop.id === cropId);
            if (refreshedCrop) setSelectedCrop(refreshedCrop);

            logAudit({
                action: "Recorded crop growth check",
                module: "Crop",
                recordName: growthCrop.name,
                entityId: growthCrop.id,
                details: `${growthData.currentSurviving} surviving • ${growthData.updateDate}`,
            });
            addTimelineEntry({
                module: "Crop",
                recordName: growthCrop.name,
                entityId: growthCrop.id,
                title: "Crop growth check recorded",
                details: `${growthData.currentSurviving}/${growthCrop.quantityPlanted} plants surviving.`,
                icon: "fact_check",
            });
            window.dispatchEvent(new CustomEvent("joross:activities-updated"));
            notify("Crop growth check saved successfully.");
        } catch (error) {
            console.error("Failed to save crop growth check:", error);
            notify(error?.message || "Unable to save crop growth check.");
        }
    };

    const handleUpdatePestDisease = async (cropId, pestId, pestData) => {
        const pestCrop = crops.find((crop) => crop.id === cropId);
        if (!pestCrop) return;

        try {
            await cropService.updatePestDisease(cropId, pestId, pestData);
            const updatedCrop = await cropService.getCrop(cropId);
            setCrops((currentCrops) =>
                currentCrops.map((crop) => (crop.id === cropId ? updatedCrop : crop))
            );
            setSelectedCrop(updatedCrop);

            logAudit({
                action: "Updated pest or disease case",
                module: "Crop",
                recordName: pestCrop.name,
                entityId: pestCrop.id,
                details: `${pestData.type || "Pest / disease"} • ${pestData.status || "Active"}`,
            });
            window.dispatchEvent(new CustomEvent("joross:activities-updated"));
            notify(
                pestData.status === "Resolved"
                    ? "Pest or disease case resolved successfully."
                    : "Pest or disease case updated successfully."
            );
        } catch (error) {
            console.error("Failed to update pest or disease record:", error);
            notify(error?.message || "Unable to update pest or disease record.");
        }
    };

    return {
        // Data
        crops,
        yieldRecords,
        cropsLoading,
        cropsError,
        cropSummary,
        filteredCrops,
        cropTypes,
        cropFields,
        harvestEligibleCrops,
        readyForHarvestCount,
        employees,

        // Permissions
        canUpdateCrops,
        canFullEditCrops,

        // Filters
        searchText,
        setSearchText,
        cropType,
        setCropType,
        statusFilter,
        setStatusFilter,
        fieldFilter,
        setFieldFilter,
        dateFilter,
        setDateFilter,
        clearFilters,

        // Modals
        addCropOpen,
        setAddCropOpen,
        addYieldOpen,
        setAddYieldOpen,
        selectedCrop,
        setSelectedCrop,
        editCrop,
        setEditCrop,
        harvestCropId,
        setHarvestCropId,

        // Actions
        handleAddCrop,
        handleEditCrop,
        handleAddYield,
        openHarvestForCrop,
        openPendingHarvestTask,
        handleConfirmReady,
        handleReopenCrop,
        reopenCropTarget,
        setReopenCropTarget,
        handleArchiveCrop,
        handleSavePestDisease,
        handleUpdatePestDisease,
        handleSaveGrowthCheck,
    };
}
