import { isRecordEditConflict } from "../../../services/recordEditing.js";
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
    const [overview, setOverview] = useState(null);
    const [overviewLoading, setOverviewLoading] = useState(true), [overviewError, setOverviewError] = useState("");
    const overviewSequence = useRef(0);
    const [cropTotal, setCropTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);
    const [yieldTotal, setYieldTotal] = useState(0);
    const [yieldLoading, setYieldLoading] = useState(true);
    const [yieldError, setYieldError] = useState("");
    const [analyticsEnabled, setAnalyticsEnabled] = useState(false);
    const enableAnalytics = useCallback(() => setAnalyticsEnabled(true), []);
    const [harvestChoices, setHarvestChoices] = useState([]);
    const requestRef = useRef(0), moreRef = useRef(false), detailsRef = useRef(0), yieldsRef = useRef(0);
    const [debouncedSearch, setDebouncedSearch] = useState("");

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

    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(searchText.trim()), 300);
        return () => window.clearTimeout(timer);
    }, [searchText]);
    const query = useMemo(() => ({ search: debouncedSearch, crop_type: cropType,
        status_filter: statusFilter, field: fieldFilter, planting_date: dateFilter || undefined }),
    [debouncedSearch, cropType, statusFilter, fieldFilter, dateFilter]);
    const loadCrops = useCallback(async () => {
        const requestId = ++requestRef.current;
        moreRef.current = false; setLoadingMore(false); setCropsLoading(true); setCropsError("");
        try {
            const page = await cropService.getCropPage({ ...query, offset: 0, limit: 50, include_overview: false });
            if (requestId !== requestRef.current) return [];
            setCrops(page.items); setCropTotal(page.total);
            return page.items;
        } catch (error) {
            if (requestId === requestRef.current) { setCropsError(error?.message || "Unable to load crop records."); }
            return [];
        } finally { if (requestId === requestRef.current) setCropsLoading(false); }
    }, [query]);
    const loadCropSummary = useCallback(async () => {
        const id = ++overviewSequence.current;
        setOverviewLoading(true); setOverviewError("");
        try {
            const value = await cropService.getSummary();
            if (id === overviewSequence.current) setOverview(value);
        } catch (error) {
            if (id === overviewSequence.current) { setOverview(null); setOverviewError(error?.message || "Unable to load crop totals."); }
        } finally { if (id === overviewSequence.current) setOverviewLoading(false); }
    }, []);
    const refreshCrops = useCallback(async () => {
        const [rows] = await Promise.all([loadCrops(), loadCropSummary()]);
        return rows;
    }, [loadCrops, loadCropSummary]);
    useEffect(() => { void loadCropSummary(); return () => { overviewSequence.current++; }; }, [loadCropSummary]);
    const loadMoreCrops = async () => {
        if (cropsLoading || moreRef.current || crops.length >= cropTotal) return;
        const requestId = requestRef.current;
        moreRef.current = true; setLoadingMore(true);
        try {
            const page = await cropService.getCropPage({ ...query, offset: crops.length, limit: 50, include_overview: false });
            if (requestId !== requestRef.current) return;
            setCrops(current => [...current, ...page.items.filter(row => !current.some(item => item.id === row.id))]);
            setCropTotal(page.total);
        } catch (error) { if (requestId === requestRef.current) setCropsError(error?.message || "Unable to load more crops."); }
        finally { if (requestId === requestRef.current) { moreRef.current = false; setLoadingMore(false); } }
    };
    const loadYields = useCallback(async (offset = 0) => {
        const requestId = ++yieldsRef.current;
        setYieldLoading(true); setYieldError("");
        try {
            const page = await cropService.getYieldPage(offset);
            if (requestId !== yieldsRef.current) return;
            setYieldRecords(current => offset ? [...current, ...page.items.filter(row => !current.some(item => item.id === row.id))] : page.items);
            setYieldTotal(page.total);
        } catch (error) { if (requestId === yieldsRef.current) setYieldError(error?.message || "Unable to load harvest history."); }
        finally { if (requestId === yieldsRef.current) setYieldLoading(false); }
    }, []);
    useEffect(() => { void loadCrops(); return () => { requestRef.current += 1; }; }, [loadCrops]);
    useEffect(() => { if (analyticsEnabled) void loadYields(); }, [loadYields, analyticsEnabled]);
    useFarmModuleUpdates(["crops", "production_sales"], () => Promise.all([refreshCrops(), ...(analyticsEnabled ? [loadYields()] : [])]), {
        editing: addCropOpen || addYieldOpen || Boolean(editCrop || selectedCrop || reopenCropTarget),
    });
    const openCropDetails = useCallback(async (crop, setter = setSelectedCrop) => {
        const requestId = ++detailsRef.current;
        try {
            const detail = await cropService.getCrop(crop.id);
            if (requestId === detailsRef.current) setter(detail);
        } catch (error) { notify(error?.message || "Unable to load crop details."); }
    }, []);
    useEffect(() => {
        if (!addYieldOpen) return;
        let active = true;
        cropService.getCrops(false, false).then(rows => { if (active) setHarvestChoices(rows); })
            .catch(error => notify(error?.message || "Unable to load harvest choices."));
        return () => { active = false; };
    }, [addYieldOpen]);

    useEffect(() => {
        if (!canUpdateCrops) return;
        workforceService.getEmployees(false)
            .then((rows) => setEmployees(Array.isArray(rows) ? rows.filter((row) => !row.is_archived && row.employment_status !== "Inactive") : []))
            .catch(() => setEmployees([]));
    }, [canUpdateCrops]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const requestedStatus = params.get("status");
        if (CROP_LIFECYCLE_FILTERS.includes(requestedStatus)) setStatusFilter(requestedStatus);
        const requestedCropId = Number(params.get("cropId") || 0);
        if (requestedCropId && params.get("addYield") !== "1") void openCropDetails({ id: requestedCropId });
        if (params.get("addYield") === "1" && canUpdateCrops) {
            if (requestedCropId) setHarvestCropId(requestedCropId);
            setAddYieldOpen(true);
        }
        if (requestedCropId || params.has("addYield")) {
            params.delete("cropId"); params.delete("addYield");
            const next = params.toString();
            window.history.replaceState(window.history.state, "", `${window.location.pathname}${next ? `?${next}` : ""}`);
        }
    }, [canUpdateCrops, openCropDetails]);

    const cropSummary = useMemo(() => [
        { id: 1, title: "Total Crops", key: "total", icon: "potted_plant", className: "total" },
        { id: 2, title: "Active Crops", key: "active", icon: "eco", className: "active" },
        { id: 3, title: "Harvested", key: "harvested", icon: "agriculture", className: "harvested" },
        { id: 4, title: "Crop Alerts", key: "alerts", icon: "warning", className: "alerts" },
    ].map(card => ({ ...card, value: overviewLoading ? "…" : overviewError || !overview ? "—" : overview[card.key] })), [overview, overviewLoading, overviewError]);
    const cropTypes = overview?.names || [];
    const cropFields = overview?.fields || [];
    const harvestEligibleCrops = useMemo(() => harvestChoices.filter(crop =>
        ["Ready for Harvest", "Harvesting"].includes(crop.status) && !crop.isArchived && !crop.pendingHarvestTaskId), [harvestChoices]);
    const readyForHarvestCount = overviewLoading ? "…" : overviewError ? "—" : overview?.ready ?? "—";
    const filteredCrops = crops;

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
            await refreshCrops();
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

            const refreshedCrops = await refreshCrops();
            const refreshedCrop =
                await cropService.getCrop(editCrop.id);

            if (selectedCrop?.id === editCrop.id) {
                setSelectedCrop(refreshedCrop);
            }



            setEditCrop(null);
            notify("Crop information updated successfully.");
        } catch (error) {
            if (isRecordEditConflict(error)) throw error;
            console.error("Failed to edit crop:", error);
            notify(error?.message || "Unable to update crop information.");
        }
    };

    const handleAddYield = async (yieldData) => {
        if (cropHarvestInFlightRef.current) {
            return;
        }
        const selectedCropRecord = harvestChoices.find(
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
            const refreshedCrops = await refreshCrops();

            if (selectedCrop?.id === yieldData.cropId) {
                const refreshedCrop = refreshedCrops.find(
                    (crop) => crop.id === yieldData.cropId
                );

                setSelectedCrop(await cropService.getCrop(yieldData.cropId));
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
            await refreshCrops();
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
        const refreshedCrops = await refreshCrops();
        const refreshed = refreshedCrops.find((crop) => crop.id === reopenCropTarget.id);
        if (refreshed && refreshed.status !== newStatus) {
            throw new Error("The crop list still shows Fully Harvested after reopening. Please retry.");
        }
        if (selectedCrop?.id === reopenCropTarget.id) {
            setSelectedCrop(await cropService.getCrop(reopenCropTarget.id));
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
            await refreshCrops();

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
        const pestCrop = crops.find((crop) => crop.id === cropId) || (selectedCrop?.id === cropId ? selectedCrop : null);

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
        const growthCrop = crops.find((crop) => crop.id === cropId) || (selectedCrop?.id === cropId ? selectedCrop : null);
        if (!growthCrop) return;

        try {
            await cropService.addGrowthRecord(cropId, growthData);
            const refreshedCrops = await refreshCrops();
            const refreshedCrop = refreshedCrops.find((crop) => crop.id === cropId);
            setSelectedCrop(await cropService.getCrop(cropId));

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
        const pestCrop = crops.find((crop) => crop.id === cropId) || (selectedCrop?.id === cropId ? selectedCrop : null);
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
        cropTotal, loadingMore, loadMoreCrops, loadCrops, overviewLoading, overviewError, loadCropSummary,
        yieldTotal, yieldLoading, yieldError, loadYields, enableAnalytics,
        analytics: overview?.analytics,
        openCropDetails,
        openEditCrop: (crop) => openCropDetails(crop, setEditCrop),
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
        refreshSelectedCrop: async () => { if (selectedCrop?.id) setSelectedCrop(await cropService.getCrop(selectedCrop.id)); await refreshCrops(); },
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
