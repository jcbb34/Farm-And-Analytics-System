"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { cropService } from "../../../services/cropService.js";
import { inventoryService } from "../../../services/inventoryService.js";
import { livestockService } from "../../../services/livestockService.js";
import { workforceService } from "../../../services/workforceService.js";
import { farmDateKey } from "../../../utils/farmCalendar.js";
import { buildTaskManagementQuery } from "../taskManagementQuery.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";


export default function useTaskManagementData({
    taskDateFilter,
    taskScheduleFilter,
    taskStatusFilter,
    taskEmployeeFilter,
    taskPriorityFilter,
    taskReassignmentFilter,
    taskSearch,
}) {
    const [tasks, setTasks] = useState([]);
    const [taskTotal, setTaskTotal] = useState(0);
    const [taskSummary, setTaskSummary] = useState(null);
    const [employees, setEmployees] = useState([]);
    const [archivedEmployees, setArchivedEmployees] = useState([]);
    const [positions, setPositions] = useState([]);
    const [inventoryItems, setInventoryItems] = useState([]);
    const [farmCrops, setFarmCrops] = useState([]);
    const [farmLivestock, setFarmLivestock] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const manualRefreshInFlightRef = useRef(false);
    const loadRequestIdRef = useRef(0);
    const moreInFlightRef = useRef(false);
    const resourcesLoadedRef = useRef(false);
    const resourcesInFlightRef = useRef(null);

    const currentQuery = useCallback(() => buildTaskManagementQuery({
        taskDateFilter, taskScheduleFilter, taskStatusFilter, taskEmployeeFilter,
        taskPriorityFilter, taskReassignmentFilter, taskSearch, todayKey: farmDateKey(),
    }), [taskDateFilter, taskScheduleFilter, taskStatusFilter, taskEmployeeFilter,
        taskPriorityFilter, taskReassignmentFilter, taskSearch]);

    const load = useCallback(async () => {
        const requestId = loadRequestIdRef.current + 1;
        loadRequestIdRef.current = requestId;
        setLoading(true);
        setError("");
        try {
            const [page, employeeData, summary] = await Promise.all([
                workforceService.getTasksPage({ ...currentQuery(), limit: 25 }),
                workforceService.getEmployees(),
                workforceService.getTaskManagementSummary(),
            ]);
            if (requestId !== loadRequestIdRef.current) return;
            setTasks(page?.items || []);
            setTaskTotal(page?.total || 0);
            setTaskSummary(summary);
            setEmployees(employeeData || []);
        } catch (loadError) {
            if (requestId !== loadRequestIdRef.current) return;
            setError(loadError?.message || "Unable to load workforce tasks.");
        } finally {
            if (requestId === loadRequestIdRef.current) setLoading(false);
        }
    }, [currentQuery]);

    const loadMore = useCallback(async () => {
        if (moreInFlightRef.current || tasks.length >= taskTotal) return;
        moreInFlightRef.current = true;
        const requestId = loadRequestIdRef.current;
        try {
            const page = await workforceService.getTasksPage({
                ...currentQuery(), offset: tasks.length, limit: 25,
            });
            if (requestId !== loadRequestIdRef.current) return;
            setTasks((current) => [...current, ...(page.items || [])]);
            setTaskTotal(page.total);
        } catch (loadError) {
            if (requestId === loadRequestIdRef.current) setError(loadError?.message || "Unable to load more tasks.");
        } finally {
            moreInFlightRef.current = false;
        }
    }, [currentQuery, tasks.length, taskTotal]);

    const loadResources = useCallback(async ({ force = false } = {}) => {
        if (resourcesLoadedRef.current && !force) return;
        if (resourcesInFlightRef.current) return resourcesInFlightRef.current;
        const pending = Promise.allSettled([
            inventoryService.getInventory(false, false), cropService.getCrops(false, false),
            livestockService.getLivestock(false),
        ]).then(([inventory, crops, livestock]) => {
            if (inventory.status === "fulfilled") setInventoryItems(inventory.value || []);
            if (crops.status === "fulfilled") setFarmCrops(crops.value || []);
            if (livestock.status === "fulfilled") setFarmLivestock(livestock.value || []);
            resourcesLoadedRef.current = [inventory, crops, livestock].every((result) => result.status === "fulfilled");
        }).finally(() => { resourcesInFlightRef.current = null; });
        resourcesInFlightRef.current = pending;
        return pending;
    }, []);

    const loadSupportData = useCallback(async () => {
        const results = await Promise.allSettled([
            workforceService.getArchivedEmployees(),
            workforceService.getPositions(),
        ]);
        const [archived, positionData] = results;
        if (archived.status === "fulfilled") setArchivedEmployees(archived.value || []);
        if (positionData.status === "fulfilled") setPositions(positionData.value || []);
    }, []);

    const refreshAll = useCallback(async () => {
        await Promise.all([load(), loadSupportData(), loadResources({ force: true })]);
    }, [load, loadSupportData, loadResources]);

    const handleManualRefresh = useCallback(async () => {
        if (manualRefreshInFlightRef.current) return;
        manualRefreshInFlightRef.current = true;
        setRefreshing(true);
        try {
            await refreshAll();
        } finally {
            manualRefreshInFlightRef.current = false;
            setRefreshing(false);
        }
    }, [refreshAll]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        loadSupportData();
    }, [loadSupportData]);
    useFarmModuleUpdates(["tasks", "employees", "calendar"], load);

    return {
        archivedEmployees,
        employees,
        error,
        farmCrops,
        farmLivestock,
        handleManualRefresh,
        inventoryItems,
        load,
        loadMore,
        loadResources,
        loadSupportData,
        loading,
        positions,
        refreshing,
        refreshAll,
        setArchivedEmployees,
        setEmployees,
        setError,
        setTasks,
        tasks,
        taskTotal,
        taskSummary,
    };
}
