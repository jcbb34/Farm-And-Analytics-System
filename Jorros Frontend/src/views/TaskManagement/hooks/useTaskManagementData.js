"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { workforceService } from "../../../services/workforceService.js";
import { farmDateKey } from "../../../utils/farmCalendar.js";
import { buildTaskManagementQuery } from "../taskManagementQuery.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";

export default function useTaskManagementData({
    taskDateFilter, taskScheduleFilter, taskStatusFilter, taskEmployeeFilter,
    taskPriorityFilter, taskReassignmentFilter, taskSearch,
}) {
    const [tasks, setTasks] = useState([]);
    const [taskTotal, setTaskTotal] = useState(0);
    const [taskSummary, setTaskSummary] = useState(null);
    const [employees, setEmployees] = useState([]);
    const [archivedEmployees, setArchivedEmployees] = useState([]);
    const [positions, setPositions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [summaryLoading, setSummaryLoading] = useState(true);
    const [summaryError, setSummaryError] = useState("");
    const [employeesLoading, setEmployeesLoading] = useState(true);
    const [employeesError, setEmployeesError] = useState("");
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const manualRefreshInFlightRef = useRef(false);
    const loadRequestIdRef = useRef(0), taskRequest = useRef(null);
    const summarySequence = useRef(0), employeeSequence = useRef(0);
    const moreInFlightRef = useRef(false);

    const currentQuery = useCallback(() => buildTaskManagementQuery({
        taskDateFilter, taskScheduleFilter, taskStatusFilter, taskEmployeeFilter,
        taskPriorityFilter, taskReassignmentFilter, taskSearch, todayKey: farmDateKey(),
    }), [taskDateFilter, taskScheduleFilter, taskStatusFilter, taskEmployeeFilter,
        taskPriorityFilter, taskReassignmentFilter, taskSearch]);

    // Searches only reload their matching tasks, independently of employee and summary reads.
    const load = useCallback(async () => {
        const requestId = ++loadRequestIdRef.current;
        taskRequest.current?.abort();
        const controller = new AbortController(); taskRequest.current = controller;
        moreInFlightRef.current = false;
        setLoading(true); setError("");
        try {
            const page = await workforceService.getTasksPage({ ...currentQuery(), limit: 25 }, { signal: controller.signal });
            if (requestId !== loadRequestIdRef.current || controller.signal.aborted) return;
            setTasks(page?.items || []); setTaskTotal(page?.total || 0);
        } catch (failure) {
            if (requestId === loadRequestIdRef.current && !controller.signal.aborted)
                setError(failure?.message || "Unable to load workforce tasks.");
        } finally {
            if (requestId === loadRequestIdRef.current) { setLoading(false); taskRequest.current = null; }
        }
    }, [currentQuery]);

    const loadSummary = useCallback(async () => {
        const id = ++summarySequence.current;
        setSummaryLoading(true); setSummaryError("");
        try {
            const summary = await workforceService.getTaskManagementSummary();
            if (id === summarySequence.current) setTaskSummary(summary);
        } catch (failure) {
            if (id === summarySequence.current) setSummaryError(failure?.message || "Unable to load task totals.");
        } finally { if (id === summarySequence.current) setSummaryLoading(false); }
    }, []);

    const loadEmployees = useCallback(async () => {
        const id = ++employeeSequence.current;
        setEmployeesLoading(true); setEmployeesError("");
        try {
            const rows = await workforceService.getEmployees();
            if (id === employeeSequence.current) setEmployees(rows || []);
        } catch (failure) {
            if (id === employeeSequence.current) setEmployeesError(failure?.message || "Unable to load employees.");
        } finally { if (id === employeeSequence.current) setEmployeesLoading(false); }
    }, []);

    const refreshTaskState = useCallback(() => Promise.all([load(), loadSummary(), loadEmployees()]), [load, loadSummary, loadEmployees]);
    const loadMore = useCallback(async () => {
        if (loading || moreInFlightRef.current || tasks.length >= taskTotal) return;
        moreInFlightRef.current = true;
        const requestId = loadRequestIdRef.current;
        const controller = new AbortController(); taskRequest.current = controller;
        try {
            const page = await workforceService.getTasksPage({ ...currentQuery(), offset: tasks.length, limit: 25 }, { signal: controller.signal });
            if (requestId !== loadRequestIdRef.current || controller.signal.aborted) return;
            setTasks(current => [...current, ...(page.items || [])]); setTaskTotal(page.total);
        } catch (failure) {
            if (requestId === loadRequestIdRef.current && !controller.signal.aborted)
                setError(failure?.message || "Unable to load more tasks.");
        } finally {
            if (requestId === loadRequestIdRef.current) { moreInFlightRef.current = false; taskRequest.current = null; }
        }
    }, [currentQuery, loading, tasks.length, taskTotal]);

    const loadSupportData = useCallback(async () => {
        const [archived, positionData] = await Promise.allSettled([
            workforceService.getArchivedEmployees(), workforceService.getPositions(),
        ]);
        if (archived.status === "fulfilled") setArchivedEmployees(archived.value || []);
        if (positionData.status === "fulfilled") setPositions(positionData.value || []);
    }, []);

    const refreshAll = useCallback(() => Promise.all([
        refreshTaskState(), loadSupportData(),
    ]), [refreshTaskState, loadSupportData]);
    const handleManualRefresh = useCallback(async () => {
        if (manualRefreshInFlightRef.current) return;
        manualRefreshInFlightRef.current = true; setRefreshing(true);
        try { await refreshAll(); }
        finally { manualRefreshInFlightRef.current = false; setRefreshing(false); }
    }, [refreshAll]);

    useEffect(() => {
        void load();
        return () => { ++loadRequestIdRef.current; taskRequest.current?.abort(); moreInFlightRef.current = false; };
    }, [load]);
    useEffect(() => {
        void loadSummary(); void loadEmployees(); void loadSupportData();
        return () => { ++summarySequence.current; ++employeeSequence.current; };
    }, [loadSummary, loadEmployees, loadSupportData]);
    useFarmModuleUpdates(["tasks", "employees", "calendar"], refreshTaskState);

    return {
        archivedEmployees, employees, employeesLoading, employeesError, error,
        handleManualRefresh, load: refreshTaskState, loadMore,
        loadSupportData, loadEmployees, loadSummary, loading, positions,
        refreshing, refreshAll, setArchivedEmployees, setEmployees, setError, setTasks,
        tasks, taskTotal, taskSummary, summaryLoading, summaryError,
    };
}
