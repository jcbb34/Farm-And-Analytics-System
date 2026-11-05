"use client";
import { ArchiveRecords } from "../../components/Archives/Archives.jsx";

import { useVoidAuthorization } from "../../context/VoidAuthorizationContext.jsx";

import { personalDetailsPayload, validatePersonalDetails } from "../../components/PersonalDetails/personalDetails.js";
import { initialObservation, observationPayload, validateObservation } from "../../components/Monitoring/monitoring.js";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import "../../components/FarmEvents/FarmEvents.css";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { workforceService } from "../../services/workforceService.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../../services/idempotencyKey.js";
import {
    confirmAction,
    promptAction,
    useNotification,
} from "../../context/NotificationContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import WorkSubmissionReviewModal from "./WorkSubmissionReviewModal.jsx";
import CareProtocolManager from "./CareProtocolManager.jsx";
import { makeWeeklySchedule, normalizeWeeklySchedule, validateWeeklySchedule } from "../../components/WeeklyScheduleEditor/weeklySchedule.js";
import LeaveRequestsPanel from "./LeaveRequestsPanel.jsx";
import EmployeeWorkScheduleModal from "./EmployeeWorkScheduleModal.jsx";
import AssignmentsPanel, {
    formatSubmissionDate,
    HISTORICAL_TASK_STATUSES,
    isMissedAssignment,
    OPEN_TASK_STATUSES,
    REASSIGNABLE_TASK_STATUSES,
    taskDisplayPriority,
} from "./components/AssignmentsPanel.jsx";
import TaskManagementTabs from "./components/TaskManagementTabs.jsx";
import TaskSummaryCards from "./components/TaskSummaryCards.jsx";
import { EmployeeArchivesPanel, EmployeesPanel } from "./components/EmployeePanels.jsx";
import TaskManagementModals from "./components/TaskManagementModals.jsx";
import useTaskManagementData from "./hooks/useTaskManagementData.js";
import {
    today,
    addDaysToDateKey,
    EMPTY_TASK,
    EMPTY_ASSISTED_SUBMISSION,
    EMPTY_EMPLOYEE,
    resourceFitsTask,
    normalizeRecommendationText,
    getTaskRecommendationProfile,
    scoreEmployeeForTask,
} from "./taskManagementUtils.js";
import { parseTaskManagementNavigation } from "./taskManagementNavigation.js";
import "./TaskManagement.css";

function TaskManagement() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const navigation = useMemo(() => parseTaskManagementNavigation(searchParams), [searchParams]);
    const { hasPermission } = useAuth();
    const canManageCareProtocols = hasPermission("*");
    const canManageLeaveRequests = hasPermission("*") || hasPermission("workforce:manage") || hasPermission("workforce:attendance");
    const notification = useNotification();
    const [tab, setTab] = useState(() => navigation.tab);
    const [taskScheduleFilter, setTaskScheduleFilter] = useState(() => navigation.date ? "All" : "Actionable Now");
    const [taskDateFilter, setTaskDateFilter] = useState(() => navigation.date);
    const [taskStatusFilter, setTaskStatusFilter] = useState("All");
    const [taskEmployeeFilter, setTaskEmployeeFilter] = useState(() => navigation.employeeId || "All");
    const [taskSearch, setTaskSearch] = useState("");
    const [debouncedTaskSearch, setDebouncedTaskSearch] = useState("");
    const [taskPriorityFilter, setTaskPriorityFilter] = useState("All");
    const [taskReassignmentFilter, setTaskReassignmentFilter] = useState(() => navigation.assignmentState);
    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedTaskSearch(taskSearch), 300);
        return () => window.clearTimeout(timer);
    }, [taskSearch]);
    const {
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
    } = useTaskManagementData({
        taskDateFilter,
        taskScheduleFilter,
        taskStatusFilter,
        taskEmployeeFilter,
        taskPriorityFilter,
        taskReassignmentFilter,
        taskSearch: debouncedTaskSearch,
    });
    const [positionSearch, setPositionSearch] = useState("");
    const [repairingAccountLinks, setRepairingAccountLinks] = useState(false);
    const [showTaskForm, setShowTaskForm] = useState(false);
    const [taskSaving, setTaskSaving] = useState(false);
    const [existingTaskId, setExistingTaskId] = useState(null);
    const taskSavingRef = useRef(false);
    const taskCreateRequestRef = useRef(null);
    const [showEmployeeForm, setShowEmployeeForm] = useState(false);
    const [editingEmployeeId, setEditingEmployeeId] = useState(null);
    const [employeeAssignmentOptions, setEmployeeAssignmentOptions] = useState({ crops: [], livestock: [] });
    const [employeeAssignmentsLoading, setEmployeeAssignmentsLoading] = useState(false);
    const [employeeAssignmentsLoaded, setEmployeeAssignmentsLoaded] = useState(false);
    const [viewEmployee, setViewEmployee] = useState(null);
    const [viewEmployeeAssignments, setViewEmployeeAssignments] = useState({ crops: [], livestock: [] });
    const [viewEmployeeTasks, setViewEmployeeTasks] = useState([]);
    const [viewEmployeeLoading, setViewEmployeeLoading] = useState(false);
    const [scheduleEmployee, setScheduleEmployee] = useState(null);
    const [scheduleEffectiveDate, setScheduleEffectiveDate] = useState("");
    const [employeeAction, setEmployeeAction] = useState(null);
    const [archiveReason, setArchiveReason] = useState("");
    const [reassignTask, setReassignTask] = useState(null);
    const [reassignEmployeeId, setReassignEmployeeId] = useState("");
    const [reassignSearch, setReassignSearch] = useState("");
    const [reassignSaving, setReassignSaving] = useState(false);
    const [assistedTask, setAssistedTask] = useState(null);
    const [assistedForm, setAssistedForm] = useState(EMPTY_ASSISTED_SUBMISSION);
    const [assistedSaving, setAssistedSaving] = useState(false);
    const [assistedCorrectionMode, setAssistedCorrectionMode] = useState(false);
    const assistedSubmitRequestRef = useRef(null);
    const [reviewModalTaskId, setReviewModalTaskId] = useState(null);
    const [reviewReport, setReviewReport] = useState(null);
    const [reviewLoading, setReviewLoading] = useState(false);
    const [reviewLoadError, setReviewLoadError] = useState("");
    const [reviewActionError, setReviewActionError] = useState("");
    const [reviewProcessingAction, setReviewProcessingAction] = useState("");
    const reviewActionInFlightRef = useRef(false);
    const voidActionInFlightRef = useRef(false);
    const [taskDisplayLimit, setTaskDisplayLimit] = useState(100);
    const [focusedTaskId, setFocusedTaskId] = useState(() => navigation.taskId);
    const [focusedTaskRecord, setFocusedTaskRecord] = useState(null);
    const [focusedEmployeeId, setFocusedEmployeeId] = useState(() => navigation.tab === "employees" ? navigation.employeeId : "");
    const [focusedLeaveRequestId, setFocusedLeaveRequestId] = useState(() => navigation.leaveRequestId);
    const [navigationReturnTo, setNavigationReturnTo] = useState(() => navigation.returnTo);
    const dismissLeaveDeepLink = useCallback(() => {
        setFocusedLeaveRequestId("");
        if (!searchParams.has("leaveRequestId")) return;
        const nextParams = new URLSearchParams(searchParams.toString());
        nextParams.delete("leaveRequestId");
        router.replace(`/task-management${nextParams.size ? `?${nextParams.toString()}` : ""}`, { scroll: false });
    }, [router, searchParams]);
    const closeWorkSchedule = useCallback(() => {
        setScheduleEmployee(null);
        setScheduleEffectiveDate("");
        if (searchParams.get("action") !== "work-schedule") return;
        setFocusedEmployeeId("");
        const nextParams = new URLSearchParams(searchParams.toString());
        nextParams.delete("action");
        nextParams.delete("employeeId");
        nextParams.delete("scheduleDate");
        router.replace(`/task-management${nextParams.size ? `?${nextParams.toString()}` : ""}`, { scroll: false });
    }, [router, searchParams]);
    const deepLinkEmployeeOpenedRef = useRef("");
    const deepLinkAssistedOpenedRef = useRef("");
    const [taskForm, setTaskForm] = useState(EMPTY_TASK);
    const [employeeForm, setEmployeeForm] = useState(EMPTY_EMPLOYEE);
    useEffect(() => {
        if (showTaskForm || assistedTask || showEmployeeForm) void loadResources();
    }, [showTaskForm, assistedTask, showEmployeeForm, loadResources]);

    const localStats = useMemo(() => {
        const todayKey = today();
        return {
            pending: tasks.filter((x) => !x.work_suspended && x.status === "Pending" && x.activity_date <= todayKey).length,
            progress: tasks.filter((x) => !x.work_suspended && x.status === "In Progress" && x.activity_date <= todayKey).length,
            review: tasks.filter((x) => x.status === "Submitted for Review").length,
            held: tasks.filter((x) => x.work_suspended).length,
            overdue: tasks.filter((x) => !x.work_suspended && !["Completed", "Cancelled", "Resolved", "Voided"].includes(x.status) && x.activity_date < todayKey).length,
            reassign: tasks.filter((x) => !x.work_suspended && x.needs_reassignment && OPEN_TASK_STATUSES.has(x.status)).length,
        };
    }, [tasks]);
    const stats = taskSummary || localStats;

    const allEmployeesById = useMemo(() => new Map(
        [...employees, ...archivedEmployees].map((employee) => [Number(employee.id), employee]),
    ), [employees, archivedEmployees]);

    const assistedEmployeeOptions = useMemo(() => {
        if (!assistedTask) return [];
        const assignedId = Number(assistedTask.assigned_employee_id || 0);
        return [...employees, ...archivedEmployees]
            .filter((employee, index, list) => list.findIndex((item) => Number(item.id) === Number(employee.id)) === index)
            .filter((employee) => employee.employment_status === "Active" || Number(employee.id) === assignedId)
            .sort((a, b) => {
                if (Number(a.id) === assignedId) return -1;
                if (Number(b.id) === assignedId) return 1;
                return a.full_name.localeCompare(b.full_name);
            });
    }, [assistedTask, employees, archivedEmployees]);

    const assistedResourceItems = useMemo(() => {
        if (!assistedTask) return [];
        const taskText = [assistedTask.name, assistedTask.category, assistedTask.instructions].filter(Boolean).join(" ");
        return inventoryItems
            .filter((item) => resourceFitsTask(item, assistedTask.source_module, taskText))
            .sort((a, b) => `${a.category} ${a.name}`.localeCompare(`${b.category} ${b.name}`));
    }, [assistedTask, inventoryItems]);

    const assistedSelectedInventoryItem = useMemo(
        () => inventoryItems.find((item) => String(item.id) === String(assistedForm.inventory_item_id)) || null,
        [inventoryItems, assistedForm.inventory_item_id],
    );
    const assistedIsCropHarvest = Boolean(
        assistedTask?.source_module === "Crop" && assistedTask?.source_type === "crop_harvest",
    );

    const taskSourceOptions = useMemo(() => {
        if (taskForm.source_module === "Crop") return farmCrops;
        if (taskForm.source_module === "Livestock") return farmLivestock;
        if (taskForm.source_module === "Inventory") return inventoryItems;
        return [];
    }, [taskForm.source_module, farmCrops, farmLivestock, inventoryItems]);

    const manualTaskResourceItems = useMemo(() => {
        const taskText = [taskForm.name, taskForm.category, taskForm.instructions].filter(Boolean).join(" ");
        return inventoryItems
            .filter((item) => resourceFitsTask(item, taskForm.source_module, taskText))
            .sort((a, b) => `${a.category} ${a.name}`.localeCompare(`${b.category} ${b.name}`));
    }, [taskForm.source_module, taskForm.name, taskForm.category, taskForm.instructions, inventoryItems]);

    const selectedTaskInventoryItem = useMemo(
        () => inventoryItems.find((item) => String(item.id) === String(taskForm.planned_inventory_item_id)) || null,
        [inventoryItems, taskForm.planned_inventory_item_id],
    );

    const taskPlannedQuantityNumber = useMemo(() => {
        if (taskForm.planned_quantity === "" || taskForm.planned_quantity == null) return null;
        const value = Number(taskForm.planned_quantity);
        return Number.isFinite(value) ? value : null;
    }, [taskForm.planned_quantity]);

    const taskAssignmentStockError = useMemo(() => {
        if (!selectedTaskInventoryItem) return "";
        if (selectedTaskInventoryItem.expirationDate && taskForm.activity_date > selectedTaskInventoryItem.expirationDate) return "The selected stock expires before the work date. Choose valid stock.";
        if (taskPlannedQuantityNumber == null) return "";
        const available = Number(selectedTaskInventoryItem.quantity || 0);
        if (taskPlannedQuantityNumber <= available + 0.0000001) return "";
        return `Insufficient stock. Only ${available.toLocaleString(undefined, { maximumFractionDigits: 3 })} ${selectedTaskInventoryItem.unit} of ${selectedTaskInventoryItem.name} is available.`;
    }, [selectedTaskInventoryItem, taskPlannedQuantityNumber, taskForm.activity_date]);

    const taskStatusOptions = useMemo(() => [
        "All",
        "Missed",
        ...Array.from(new Set([
            "Pending", "In Progress", "Submitted for Review", "Returned",
            "Completed", "Resolved", "Cancelled", "Voided",
            ...tasks.map((task) => task.status).filter(Boolean),
        ])),
    ], [tasks]);

    const taskPriorityOptions = useMemo(() => [
        "All",
        ...Array.from(new Set(tasks.map((task) => task.priority).filter(Boolean))).sort(),
    ], [tasks]);

    const filteredTasks = useMemo(() => {
        const search = taskSearch.trim().toLowerCase();
        return tasks.filter((task) => {
            const employee = task.assigned_employee_id ? allEmployeesById.get(Number(task.assigned_employee_id)) : null;
            const employeeName = task.employee_name || employee?.full_name || task.previous_employee_name || "";
            const searchText = [
                task.name, task.activity_code, task.category, task.related_to, task.location,
                employeeName, task.status, task.priority, task.reassignment_reason,
                task.assignment_source, task.original_employee_name, task.covering_employee_name,
            ].filter(Boolean).join(" ").toLowerCase();

            if (search && !searchText.includes(search)) return false;
            if (taskStatusFilter === "Missed" && !isMissedAssignment(task)) return false;
            if (taskStatusFilter !== "All" && taskStatusFilter !== "Missed" && task.status !== taskStatusFilter) return false;
            if (taskPriorityFilter !== "All" && task.priority !== taskPriorityFilter) return false;
            if (taskEmployeeFilter === "Unassigned" && task.assigned_employee_id) return false;
            if (taskEmployeeFilter !== "All" && taskEmployeeFilter !== "Unassigned" && String(task.assigned_employee_id || "") !== taskEmployeeFilter) return false;
            if (taskReassignmentFilter === "Needs Reassignment" && !task.needs_reassignment) return false;
            if (taskReassignmentFilter === "No Reassignment" && task.needs_reassignment) return false;
            if (taskReassignmentFilter === "Leave Coverage" && task.assignment_source !== "Leave Coverage") return false;

            if (taskDateFilter && task.activity_date !== taskDateFilter) return false;
            const todayKey = today();
            const nextWeekKey = addDaysToDateKey(todayKey, 7);
            if (taskScheduleFilter === "Actionable Now") {
                const actionable = task.activity_date <= todayKey
                    ? (!HISTORICAL_TASK_STATUSES.has(task.status) || task.activity_date === todayKey)
                    : (task.status === "Submitted for Review" || task.status === "Returned" || task.needs_reassignment);
                if (!actionable) return false;
            }
            if (taskScheduleFilter === "Today" && task.activity_date !== todayKey) return false;
            if (taskScheduleFilter === "Missed / Overdue" && !isMissedAssignment(task)) return false;
            if (taskScheduleFilter === "Upcoming" && !(task.activity_date > todayKey && !HISTORICAL_TASK_STATUSES.has(task.status))) return false;
            if (taskScheduleFilter === "Next 7 Days" && !(task.activity_date > todayKey && task.activity_date <= nextWeekKey && !HISTORICAL_TASK_STATUSES.has(task.status))) return false;
            return true;
        }).sort((a, b) => taskDisplayPriority(a) - taskDisplayPriority(b));
    }, [
        tasks, allEmployeesById, taskSearch, taskStatusFilter, taskPriorityFilter,
        taskEmployeeFilter, taskReassignmentFilter, taskScheduleFilter, taskDateFilter,
    ]);

    const visibleTasks = useMemo(() => {
        const page = filteredTasks.slice(0, taskDisplayLimit);
        if (!focusedTaskId || page.some((task) => String(task.id) === String(focusedTaskId))) return page;
        const focused = filteredTasks.find((task) => String(task.id) === String(focusedTaskId))
            || (String(focusedTaskRecord?.id) === String(focusedTaskId) ? focusedTaskRecord : null);
        if (!focused) return page;
        return [focused, ...page.slice(0, Math.max(0, taskDisplayLimit - 1))];
    }, [filteredTasks, taskDisplayLimit, focusedTaskId, focusedTaskRecord]);

    useEffect(() => {
        if (tab !== "tasks" || !focusedTaskId || loading ||
            tasks.some((item) => String(item.id) === String(focusedTaskId))) return;
        let cancelled = false;
        workforceService.getTaskDetail(focusedTaskId).then((item) => {
            if (!cancelled) setFocusedTaskRecord(item);
        }).catch(() => { if (!cancelled) setFocusedTaskRecord(null); });
        return () => { cancelled = true; };
    }, [tab, focusedTaskId, loading, tasks]);

    useEffect(() => {
        setTaskDisplayLimit(100);
    }, [taskSearch, taskStatusFilter, taskPriorityFilter, taskEmployeeFilter, taskReassignmentFilter, taskScheduleFilter, taskDateFilter]);

    const clearTaskFilters = () => {
        setTaskSearch("");
        setTaskStatusFilter("All");
        setTaskScheduleFilter("Actionable Now");
        setTaskPriorityFilter("All");
        setTaskEmployeeFilter("All");
        setTaskReassignmentFilter("All");
        setTaskDateFilter("");
        setFocusedTaskId("");
        setTaskDisplayLimit(100);
    };

    const taskFiltersAreDefault = taskSearch === ""
        && taskStatusFilter === "All"
        && taskScheduleFilter === "Actionable Now"
        && taskPriorityFilter === "All"
        && taskEmployeeFilter === "All"
        && taskReassignmentFilter === "All"
        && taskDateFilter === "";

    const positionGroups = useMemo(() => positions.reduce((groups, position) => {
        if (!groups[position.category]) groups[position.category] = [];
        groups[position.category].push(position);
        return groups;
    }, {}), [positions]);

    const filteredPositionGroups = useMemo(() => {
        const query = positionSearch.trim().toLowerCase();
        if (!query) return positionGroups;
        return Object.fromEntries(
            Object.entries(positionGroups)
                .map(([category, items]) => [category, items.filter((position) =>
                    `${position.name} ${position.category}`.toLowerCase().includes(query)
                )])
                .filter(([, items]) => items.length),
        );
    }, [positionGroups, positionSearch]);

    const selectedPrimaryPosition = useMemo(
        () => positions.find((item) => String(item.id) === String(employeeForm.primary_position_id)) || null,
        [positions, employeeForm.primary_position_id],
    );

    const selectedAdditionalPositions = useMemo(
        () => positions.filter((item) => employeeForm.additional_position_ids.includes(String(item.id))),
        [positions, employeeForm.additional_position_ids],
    );

    const reassignProfile = useMemo(() => getTaskRecommendationProfile(reassignTask), [reassignTask]);

    const reassignCandidates = useMemo(() => {
        if (!reassignTask) return [];
        const query = normalizeRecommendationText(reassignSearch);
        return employees
            .filter((employee) => employee.employment_status === "Active" && !employee.is_archived)
            .filter((employee) => employee.id !== reassignTask.assigned_employee_id)
            .filter((employee) => {
                if (!query) return true;
                const searchable = normalizeRecommendationText([
                    employee.employee_code,
                    employee.full_name,
                    employee.assigned_area,
                    ...(employee.positions || []).flatMap((position) => [position.name, position.category]),
                ].filter(Boolean).join(" "));
                return searchable.includes(query);
            })
            .map((employee) => scoreEmployeeForTask(employee, reassignProfile))
            .sort((a, b) => {
                if (b.score !== a.score) return b.score - a.score;
                if (a.hasPrimaryMatch !== b.hasPrimaryMatch) return a.hasPrimaryMatch ? -1 : 1;
                return a.employee.full_name.localeCompare(b.employee.full_name);
            });
    }, [employees, reassignTask, reassignProfile, reassignSearch]);

    const recommendedReassignCandidates = useMemo(
        () => reassignCandidates.filter((candidate) => candidate.score > 0),
        [reassignCandidates],
    );

    const otherReassignCandidates = useMemo(
        () => reassignCandidates.filter((candidate) => candidate.score <= 0),
        [reassignCandidates],
    );

    const closeTaskModal = useCallback(() => {
        if (taskSavingRef.current) return;
        setShowTaskForm(false);
    }, []);

    const closeEmployeeModal = useCallback(() => {
        setShowEmployeeForm(false);
        setEditingEmployeeId(null);
        setEmployeeForm(EMPTY_EMPLOYEE);
        setEmployeeAssignmentOptions({ crops: [], livestock: [] });
        setEmployeeAssignmentsLoading(false);
        setEmployeeAssignmentsLoaded(false);
        setPositionSearch("");
    }, []);

    const closeViewEmployeeModal = useCallback(() => {
        setViewEmployee(null);
        setViewEmployeeAssignments({ crops: [], livestock: [] });
        setViewEmployeeTasks([]);
        setViewEmployeeLoading(false);
    }, []);

    const closeEmployeeActionModal = useCallback(() => {
        setEmployeeAction(null);
        setArchiveReason("");
    }, []);

    const closeReassignModal = useCallback(() => {
        setReassignTask(null);
        setReassignEmployeeId("");
        setReassignSearch("");
        setReassignSaving(false);
    }, []);

    const closeAssistedModal = useCallback(() => {
        clearStableIdempotencyKey(assistedSubmitRequestRef);
        setAssistedTask(null);
        setAssistedForm(EMPTY_ASSISTED_SUBMISSION);
        setAssistedSaving(false);
        setAssistedCorrectionMode(false);
        if (searchParams.get("action") !== "assisted-submission") return;
        const nextParams = new URLSearchParams(searchParams.toString());
        nextParams.delete("action");
        router.replace(`/task-management${nextParams.size ? `?${nextParams.toString()}` : ""}`, { scroll: false });
    }, [router, searchParams]);

    useEffect(() => {
        if (!showTaskForm && !showEmployeeForm && !viewEmployee && !employeeAction && !reassignTask && !assistedTask) return undefined;

        const previousOverflow = document.body.style.overflow;
        const handleKeyDown = (event) => {
            if (event.key !== "Escape") return;
            if (assistedTask) closeAssistedModal();
            else if (reassignTask) closeReassignModal();
            else if (employeeAction) closeEmployeeActionModal();
            else if (viewEmployee) closeViewEmployeeModal();
            else if (showEmployeeForm) closeEmployeeModal();
            else if (showTaskForm) closeTaskModal();
        };

        document.body.style.overflow = "hidden";
        window.addEventListener("keydown", handleKeyDown);

        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", handleKeyDown);
        };
    }, [showTaskForm, showEmployeeForm, viewEmployee, employeeAction, reassignTask, assistedTask, closeTaskModal, closeEmployeeModal, closeViewEmployeeModal, closeEmployeeActionModal, closeReassignModal, closeAssistedModal]);

    const saveTask = async (event) => {
        event.preventDefault();
        if (taskSavingRef.current) return;
        taskSavingRef.current = true;
        setTaskSaving(true);
        setExistingTaskId(null);
        try {
            if (!taskForm.name.trim() || !taskForm.category.trim()) {
                notification.error("Enter a task name and category.", "Task Details");
                return;
            }
            if (taskAssignmentStockError) {
                notification.error(taskAssignmentStockError, "Insufficient Stock");
                return;
            }
            const selectedEmployee = taskForm.employee_id
                ? employees.find((employee) => String(employee.id) === String(taskForm.employee_id))
                : null;
            const selectedBackup = taskForm.backup_employee_id
                ? employees.find((employee) => String(employee.id) === String(taskForm.backup_employee_id))
                : null;
            if (selectedEmployee && !selectedEmployee.portal_assignment_ready) {
                notification.error(`${selectedEmployee.full_name} cannot receive portal work: ${selectedEmployee.account_status || "No Login Account"}. Link or create the employee login first.`, "Employee Account Required");
                return;
            }
            if (selectedBackup && !selectedBackup.portal_assignment_ready) {
                notification.error(`${selectedBackup.full_name} cannot be used as a task backup until an active Employee login is linked.`, "Backup Account Required");
                return;
            }
            let allowUnavailableOverride = false;
            if (selectedEmployee && taskForm.activity_date) {
                try {
                    const availability = await workforceService.getAvailability(taskForm.activity_date, taskForm.activity_date, selectedEmployee.id);
                    const day = availability?.[0];
                    if (day && !day.available) {
                        allowUnavailableOverride = await confirmAction({
                            title: "Employee Unavailable",
                            message: `${selectedEmployee.full_name} is unavailable on ${taskForm.activity_date}: ${day.reason}. Assign anyway as an authorized manager override? The task will remain visible with an availability warning.`,
                            confirmText: "Assign Anyway",
                        });
                        if (!allowUnavailableOverride) return;
                    }
                } catch (err) {
                    notification.error(err?.message || "Unable to verify employee availability.", "Availability Check");
                    return;
                }
            }
            try {
                const payload = {
                    ...taskForm,
                    employee_id: taskForm.employee_id ? Number(taskForm.employee_id) : null,
                    allow_unavailable_override: allowUnavailableOverride,
                    planned_quantity: taskForm.planned_quantity === "" ? null : Number(taskForm.planned_quantity),
                    planned_unit: taskForm.planned_unit || null,
                    planned_inventory_item_id: taskForm.planned_inventory_item_id ? Number(taskForm.planned_inventory_item_id) : null,
                    planned_usage_type: taskForm.planned_usage_type || null,
                    source_module: taskForm.source_module || null,
                    source_type: taskForm.source_module ? (taskForm.source_type || "manual_work") : null,
                    source_record_id: taskForm.source_record_id ? Number(taskForm.source_record_id) : null,
                    source_path: taskForm.source_module === "Crop" ? "/crops" : taskForm.source_module === "Livestock" ? "/livestock" : taskForm.source_module === "Inventory" ? "/inventory" : null,
                    feeding_slot: taskForm.feeding_slot || null,
                    backup_employee_id: taskForm.backup_employee_id ? Number(taskForm.backup_employee_id) : null,
                    time_sensitive: Boolean(taskForm.time_sensitive),
                    controlled_rescheduling: Boolean(taskForm.controlled_rescheduling),
                    max_delay_minutes: taskForm.max_delay_minutes === "" ? null : Number(taskForm.max_delay_minutes),
                    description: taskForm.description || null,
                    instructions: taskForm.instructions || null,
                };
                const idempotencyKey = stableIdempotencyKey(taskCreateRequestRef, payload, "manual-task");
                await workforceService.createTask(payload, { idempotencyKey });
                clearStableIdempotencyKey(taskCreateRequestRef);
                notification.success("Task saved.", "Task Management");
                setTaskForm(EMPTY_TASK); setShowTaskForm(false); await load();
            } catch (err) {
                setExistingTaskId(err?.details?.existingTaskId || null);
                const message = err?.message || "Unable to create task.";
                notification.error(message, /insufficient stock/i.test(message) ? "Insufficient Stock" : "Task Error");
                if (/insufficient stock/i.test(message)) {
                    // Another task or inventory transaction may have changed stock
                    // after this modal was opened. Refresh the current stock values
                    // so the inline Assign Task warning immediately reflects it.
                    await loadSupportData();
                }
            }
        } finally {
            taskSavingRef.current = false;
            setTaskSaving(false);
        }
    };

    const closeReviewModal = useCallback(() => {
        if (reviewActionInFlightRef.current) return;
        setReviewModalTaskId(null);
        setReviewReport(null);
        setReviewLoading(false);
        setReviewLoadError("");
        setReviewActionError("");
        setReviewProcessingAction("");
    }, []);

    const loadReviewReport = useCallback(async (taskId) => {
        if (!taskId) return;
        setReviewLoading(true);
        setReviewLoadError("");
        setReviewActionError("");
        try {
            const report = await workforceService.getTaskReviewReport(taskId);
            setReviewReport(report);
        } catch (err) {
            setReviewReport(null);
            const stale = err?.status === 409;
            setReviewLoadError(stale
                ? "This submission was already reviewed or changed by another reviewer. The assignment table has been refreshed."
                : (err?.message || "Unable to load the work submission report."));
            if (stale) await load();
        } finally {
            setReviewLoading(false);
        }
    }, [load]);

    const openReviewSubmission = useCallback((task) => {
        if (!task || task.status !== "Submitted for Review") return;
        setReviewModalTaskId(task.id);
        setReviewReport(null);
        setReviewLoadError("");
        setReviewActionError("");
        loadReviewReport(task.id);
    }, [loadReviewReport]);

    const performReviewAction = useCallback(async (decision, feedback = null, options = {}) => {
        if (!reviewModalTaskId || reviewActionInFlightRef.current) return false;
        if (!["Approve", "Return"].includes(decision)) return false;
        reviewActionInFlightRef.current = true;
        setReviewProcessingAction(decision);
        setReviewActionError("");
        try {
            await workforceService.reviewTask(reviewModalTaskId, decision, feedback, options);
            const trackedInventory = Boolean(reviewReport?.resource_usage?.tracked);
            if (decision === "Approve") {
                notification.success(
                    trackedInventory
                        ? "Work approved. The approved actual inventory quantity was deducted now."
                        : "Work approved successfully.",
                    "Review Complete",
                );
            } else if (decision === "Return") {
                notification.success(
                    trackedInventory
                        ? "Work returned for correction. The pending inventory reservation was released; inventory was not deducted."
                        : "Work returned for correction.",
                    "Review Complete",
                );
            }
            setReviewModalTaskId(null);
            setReviewReport(null);
            await load();
            return true;
        } catch (err) {
            const stale = err?.status === 409 && /no longer awaiting review/i.test(err?.message || "");
            setReviewActionError(stale
                ? "This submission was already reviewed by another user. No second decision was applied. The assignment table has been refreshed."
                : (err?.message || "Unable to save this review decision."));
            if (stale) await load();
            return false;
        } finally {
            reviewActionInFlightRef.current = false;
            setReviewProcessingAction("");
        }
    }, [load, notification, reviewModalTaskId, reviewReport]);

    const requestVoid = useVoidAuthorization();
    const voidCompletedTask = async (task) => {
        if (voidActionInFlightRef.current || !task.can_void || task.status !== "Completed" || task.latest_submission?.review_status !== "Approved") return;
        voidActionInFlightRef.current = true;
        try {
            if (!await requestVoid({ action: "task", recordId: task.id, onStale: load })) return;
            notification.success("Approved work voided. Any posted inventory usage was reversed, and the reason was recorded.", "Task Voided");
            await load();
        } catch (err) {
            notification.error(err?.message || "Unable to void task.", "Void Error");
            if (err?.status === 409) await load();
        } finally { voidActionInFlightRef.current = false; }
    };

    const reassign = (task) => {
        setReassignTask(task);
        setReassignEmployeeId("");
        setReassignSearch("");
    };

    const performTaskReassignment = async () => {
        if (!reassignTask || !reassignEmployeeId) {
            notification.error("Select an employee before saving the reassignment.", "Reassign Task");
            return;
        }
        const selectedCandidate = reassignCandidates.find((candidate) => String(candidate.employee.id) === String(reassignEmployeeId));
        if (!selectedCandidate) {
            notification.error("The selected employee is not currently available for assignment.", "Reassign Task");
            return;
        }
        if (!selectedCandidate.employee.portal_assignment_ready) {
            notification.error(`${selectedCandidate.employee.full_name} cannot receive portal work: ${selectedCandidate.employee.account_status || "No Login Account"}. Link or create the employee login first.`, "Employee Account Required");
            return;
        }
        let allowUnavailableOverride = false;
        try {
            const availability = await workforceService.getAvailability(reassignTask.activity_date, reassignTask.activity_date, selectedCandidate.employee.id);
            const day = availability?.[0];
            if (day && !day.available) {
                allowUnavailableOverride = await confirmAction({
                    title: "Employee Unavailable",
                    message: `${selectedCandidate.employee.full_name} is unavailable on ${reassignTask.activity_date}: ${day.reason}. Reassign anyway as an authorized manager override? The task will remain visible with an availability warning.`,
                    confirmText: "Reassign Anyway",
                });
                if (!allowUnavailableOverride) return;
            }
        } catch (err) {
            notification.error(err?.message || "Unable to verify employee availability.", "Availability Check");
            return;
        }
        setReassignSaving(true);
        try {
            await workforceService.updateAssignment(reassignTask.id, {
                employee_id: Number(reassignEmployeeId),
                allow_unavailable_override: allowUnavailableOverride,
                reason: "Manual reassignment by authorized manager.",
            });
            notification.success(`${reassignTask.name} reassigned to ${selectedCandidate.employee.full_name}.`, "Task Reassigned");
            closeReassignModal();
            await load();
        } catch (err) {
            setReassignSaving(false);
            notification.error(err?.message || "Unable to reassign task.", "Assignment Error");
        }
    };

    const openAssistedSubmission = (task, correctionMode = false) => {
        if (!correctionMode && (task?.needs_reassignment || !task?.assigned_employee_id || task?.work_suspended)) {
            notification.warning(
                "Reassign this task to an available employee before recording work on their behalf.",
                "Reassignment Required",
            );
            return;
        }
        clearStableIdempotencyKey(assistedSubmitRequestRef);
        const defaultEmployeeId = correctionMode
            ? String(task.latest_submission?.employee_id || task.assigned_employee_id || "")
            : (task.assigned_employee_id ? String(task.assigned_employee_id) : "");
        const resourceTask = Boolean(task.resource_required);
        const cropHarvestTask = task.source_module === "Crop" && task.source_type === "crop_harvest";
        const lastActual = task.latest_submission?.actual_quantity;
        const defaultActual = lastActual != null
            ? String(lastActual)
            : resourceTask && task.planned_quantity != null
                ? String(task.planned_quantity)
                : "";
        setAssistedCorrectionMode(Boolean(correctionMode));
        setAssistedTask(task);
        setAssistedForm({
            ...EMPTY_ASSISTED_SUBMISSION,
            monitoring: task.latest_submission?.monitoring || initialObservation(task.monitoring_context),
            employee_id: defaultEmployeeId,
            inventory_item_id: task.planned_inventory_item_id ? String(task.planned_inventory_item_id) : "",
            actual_quantity: defaultActual,
            actual_unit: cropHarvestTask
                ? "kg"
                : resourceTask
                ? (task.planned_inventory_unit || task.planned_unit || "")
                : (task.latest_submission?.actual_unit || ""),
            harvest_type_intent: cropHarvestTask ? (task.latest_submission?.harvest_type_intent || "") : "",
            assisted_reason: correctionMode ? "Correct actual resource quantity" : "Employee forgot to submit",
        });
    };

    const submitAssistedWork = async (approveNow = false) => {
        if (!assistedTask) return;
        if (!assistedForm.employee_id) {
            notification.error("Select the employee who actually performed the work.", "Assisted Submission");
            return;
        }
        if (!assistedForm.assisted_reason.trim()) {
            notification.error("Enter why the manager is recording this work on behalf of the employee.", "Assisted Submission");
            return;
        }
        if (assistedTask.resource_required && !assistedTask.resource_linked && !assistedForm.inventory_item_id) {
            notification.error("Select the inventory resource used for this task.", "Assisted Submission");
            return;
        }
        if ((assistedTask.resource_required || assistedIsCropHarvest) && (!assistedForm.actual_quantity || Number(assistedForm.actual_quantity) <= 0)) {
            notification.error(
                assistedIsCropHarvest ? "Enter the actual harvest yield in kg." : "Enter the actual resource quantity used.",
                "Assisted Submission",
            );
            return;
        }
        if ((assistedTask.resource_required || assistedIsCropHarvest) && !assistedForm.actual_quantity_confirmed) {
            notification.error(
                assistedIsCropHarvest
                    ? "Confirm that the entered kg is the actual harvested yield."
                    : "Confirm that the quantity entered is the actual amount used, not only the planned amount.",
                "Actual Quantity Confirmation",
            );
            return;
        }
        if (assistedIsCropHarvest && !assistedForm.harvest_type_intent) {
            notification.error(
                "Choose Partial Harvest or Final Harvest before submitting for manager review.",
                "Harvest Type Required",
            );
            return;
        }
        if (assistedTask.requires_evidence && !assistedForm.evidence_url.trim()) {
            notification.error("Evidence is required for this task.", "Assisted Submission");
            return;
        }

        const monitoringError = validateObservation(assistedForm.monitoring, assistedTask.monitoring_context);
        if (monitoringError) { notification.error(monitoringError, "Monitoring Observation"); return; }
        if (assistedTask.monitoring_context && approveNow) { notification.error("Submit monitoring for explicit review.", "Monitoring Review"); return; }
        const payload = {
            monitoring: observationPayload(assistedForm.monitoring, assistedTask.monitoring_context),
            performed_by_employee_id: Number(assistedForm.employee_id),
            inventory_item_id: assistedForm.inventory_item_id ? Number(assistedForm.inventory_item_id) : null,
            assisted_reason: assistedForm.assisted_reason.trim(),
            actual_quantity: assistedForm.actual_quantity === "" ? null : Number(assistedForm.actual_quantity),
            actual_quantity_confirmed: Boolean(assistedForm.actual_quantity_confirmed),
            actual_unit: assistedForm.actual_unit.trim() || null,
            harvest_type_intent: assistedIsCropHarvest ? assistedForm.harvest_type_intent : null,
            evidence_url: assistedForm.evidence_url.trim() || null,
            worker_notes: assistedForm.worker_notes.trim() || null,
            problem_report: assistedForm.problem_report.trim() || null,
            approve_now: Boolean(approveNow || assistedCorrectionMode),
            correction_only: Boolean(assistedCorrectionMode),
            allow_negative_inventory: Boolean(assistedForm.allow_negative_inventory),
            inventory_override_reason: assistedForm.allow_negative_inventory
                ? assistedForm.inventory_override_reason.trim() || null
                : null,
        };
        if (payload.allow_negative_inventory && !payload.inventory_override_reason) {
            notification.error("Enter a reason for the negative-inventory override.", "Override Reason Required");
            return;
        }
        const idempotencyKey = stableIdempotencyKey(
            assistedSubmitRequestRef, payload, `assisted-task-submit:${assistedTask.id}`,
        );
        setAssistedSaving(true);
        try {
            const updatedTask = await workforceService.submitTask(assistedTask.id, payload, idempotencyKey);
            clearStableIdempotencyKey(assistedSubmitRequestRef);
            notification.success(
                assistedCorrectionMode
                    ? "Actual resource usage corrected. Inventory was adjusted by the approved difference only."
                    : updatedTask?.status === "Completed"
                        ? (assistedTask.resource_required
                            ? "Work recorded and approved. The approved actual inventory quantity was deducted."
                            : "Work recorded and approved with an audit trail.")
                        : (assistedIsCropHarvest
                            ? "Harvest work recorded for the employee and submitted for review. The crop lifecycle will change only after manager confirmation."
                            : assistedTask.resource_required
                            ? "Work recorded on behalf of the employee and submitted for review. The reported inventory quantity is reserved until approval."
                            : "Work recorded on behalf of the employee and submitted for review."),
                assistedCorrectionMode ? "Usage Corrected" : "Assisted Submission",
            );
            closeAssistedModal();
            await refreshAll();
        } catch (err) {
            setAssistedSaving(false);
            notification.error(err?.message || "Unable to record the employee's work.", "Assisted Submission");
        }
    };

    const repairEmployeeAccountLinks = async () => {
        if (repairingAccountLinks) return;
        setRepairingAccountLinks(true);
        try {
            const result = await workforceService.repairEmployeeAccountLinks();
            const repairedCount = result?.repaired?.length || 0;
            const skippedCount = result?.skipped?.length || 0;
            notification.success(`Account-link repair completed: ${repairedCount} linked, ${skippedCount} left for manual review.`, "Employee Accounts");
            await loadSupportData();
        } catch (err) {
            notification.error(err?.message || "Unable to repair employee account links.", "Employee Accounts");
        } finally {
            setRepairingAccountLinks(false);
        }
    };

    const openAddEmployee = () => {
        setEditingEmployeeId(null);
        setEmployeeForm({ ...EMPTY_EMPLOYEE, date_hired: today(), create_login_account: true, schedule_needs_setup: false, weekly_schedule: makeWeeklySchedule(today()) });
        setEmployeeAssignmentOptions({ crops: [], livestock: [] });
        setEmployeeAssignmentsLoaded(false);
        setPositionSearch("");
        setShowEmployeeForm(true);
    };

    const openEditEmployee = async (employee) => {
        const employeePositions = employee.positions || [];
        const primary = employeePositions.find((item) => item.is_primary) || employeePositions[0] || null;
        setEditingEmployeeId(employee.id);
        setEmployeeForm({
            personal_details: employee.personal_details || null,
            full_name: employee.full_name || "",
            contact_number: employee.contact_number || "",
            email: employee.email || "",
            address: employee.address || "",
            primary_position_id: primary ? String(primary.id) : "",
            additional_position_ids: employeePositions.filter((item) => !item.is_primary).map((item) => String(item.id)),
            date_hired: employee.date_hired || "",
            employment_type: employee.employment_type || "Regular",
            assigned_area: employee.assigned_area || "",
            skills: employee.skills || "",
            employment_status: employee.employment_status || "Active",
            emergency_contact_name: employee.emergency_contact_name || "",
            emergency_contact_relationship: employee.emergency_contact_relationship || "",
            emergency_contact_number: employee.emergency_contact_number || "",
            notes: employee.notes || "",
            crop_assignment_ids: [],
            livestock_assignment_ids: [],
            create_login_account: false,
            login_username: employee.login_username || "",
            login_password: "",
            login_password_confirm: "",
            has_login_account: Boolean(employee.login_user_id),
            login_status: employee.login_status || null,
            schedule_needs_setup: employee.schedule_status === "Needs Setup",
            weekly_schedule: normalizeWeeklySchedule(employee.weekly_schedule, employee.schedule_status === "Needs Setup" ? today() : (employee.date_hired || today())),
        });
        setPositionSearch("");
        setEmployeeAssignmentOptions({ crops: [], livestock: [] });
        setEmployeeAssignmentsLoaded(false);
        setEmployeeAssignmentsLoading(true);
        setShowEmployeeForm(true);
        try {
            const assignmentData = await workforceService.getEmployeeWorkAssignments(employee.id, true);
            const crops = assignmentData?.crops || [];
            const livestock = assignmentData?.livestock || [];
            setEmployeeAssignmentOptions({ crops, livestock });
            setEmployeeForm((current) => ({
                ...current,
                crop_assignment_ids: crops.filter((item) => item.is_assigned_to_employee).map((item) => String(item.id)),
                livestock_assignment_ids: livestock.filter((item) => item.is_assigned_to_employee).map((item) => String(item.id)),
            }));
            setEmployeeAssignmentsLoaded(true);
        } catch (err) {
            notification.error(err?.message || "Unable to load the employee's current farm assignments.", "Assignments Error");
        } finally {
            setEmployeeAssignmentsLoading(false);
        }
    };

    const openViewEmployee = async (employee) => {
        setViewEmployee(employee);
        setViewEmployeeAssignments({ crops: [], livestock: [] });
        setViewEmployeeTasks([]);
        setViewEmployeeLoading(true);
        try {
            const [assignmentData, employeeTasks] = await Promise.all([
                workforceService.getEmployeeWorkAssignments(employee.id, false),
                workforceService.getTasks({ employee_id: employee.id }),
            ]);
            setViewEmployeeAssignments({
                crops: assignmentData?.crops || [],
                livestock: assignmentData?.livestock || [],
            });
            setViewEmployeeTasks((employeeTasks || []).filter((task) => OPEN_TASK_STATUSES.has(task.status)));
        } catch (err) {
            notification.error(err?.message || "Unable to load employee assignment details.", "Employee View");
        } finally {
            setViewEmployeeLoading(false);
        }
    };

    const toggleEmployeeWorkAssignment = (field, id) => {
        const value = String(id);
        setEmployeeForm((current) => {
            const selected = current[field] || [];
            return {
                ...current,
                [field]: selected.includes(value)
                    ? selected.filter((item) => item !== value)
                    : [...selected, value],
            };
        });
    };

    const saveEmployeeProfile = async (event) => {
        event.preventDefault();
        const detailsError = validatePersonalDetails(employeeForm.personal_details, !editingEmployeeId);
        if (detailsError) { notification.error(detailsError, "Employee Information"); return; }
        if (!employeeForm.primary_position_id) {
            notification.error("Select a primary farm position.", "Employee Position");
            return;
        }
        const positionIds = [employeeForm.primary_position_id, ...employeeForm.additional_position_ids]
            .filter(Boolean)
            .map(Number);
        if (positionIds.length > 5) {
            notification.error("An employee can have a maximum of 5 active positions.", "Employee Position");
            return;
        }
        const scheduleError = validateWeeklySchedule(employeeForm.weekly_schedule);
        if (scheduleError) {
            notification.error(scheduleError, "Weekly Work Schedule");
            return;
        }

        const needsNewLogin = !employeeForm.has_login_account && employeeForm.create_login_account;
        if (needsNewLogin) {
            if (!employeeForm.login_username.trim()) {
                notification.error("Enter a username for the employee login.", "Login Access");
                return;
            }
            if (employeeForm.login_password.length < 8) {
                notification.error("Employee passwords must be at least 8 characters.", "Login Access");
                return;
            }
        }
        if (employeeForm.login_password || employeeForm.login_password_confirm) {
            if (employeeForm.login_password.length < 8) {
                notification.error("Employee passwords must be at least 8 characters.", "Login Access");
                return;
            }
            if (employeeForm.login_password !== employeeForm.login_password_confirm) {
                notification.error("Password and confirmation do not match.", "Login Access");
                return;
            }
        }

        const payload = {
            personal_details: personalDetailsPayload(employeeForm.personal_details),
            full_name: employeeForm.full_name.trim(),
            contact_number: employeeForm.contact_number || null,
            email: employeeForm.email || null,
            address: employeeForm.address || null,
            primary_position_id: Number(employeeForm.primary_position_id),
            position_ids: positionIds,
            date_hired: employeeForm.date_hired || null,
            employment_type: employeeForm.employment_type || null,
            assigned_area: employeeForm.assigned_area || null,
            skills: employeeForm.skills || null,
            employment_status: employeeForm.employment_status || "Active",
            emergency_contact_name: employeeForm.emergency_contact_name || null,
            emergency_contact_relationship: employeeForm.emergency_contact_relationship || null,
            emergency_contact_number: employeeForm.emergency_contact_number || null,
            notes: employeeForm.notes || null,
            weekly_schedule: {
                ...employeeForm.weekly_schedule,
                backup_employee_id: employeeForm.weekly_schedule.backup_employee_id ? Number(employeeForm.weekly_schedule.backup_employee_id) : null,
                effective_to: employeeForm.weekly_schedule.effective_to || null,
            },
            ...(employeeForm.has_login_account ? {
                login_username: employeeForm.login_username.trim(),
                ...(employeeForm.login_password ? { login_password: employeeForm.login_password } : {}),
            } : employeeForm.create_login_account ? {
                create_login_account: true,
                login_username: employeeForm.login_username.trim(),
                login_password: employeeForm.login_password,
            } : { create_login_account: false }),
            ...(editingEmployeeId && employeeAssignmentsLoaded ? {
                crop_assignment_ids: (employeeForm.crop_assignment_ids || []).map(Number),
                livestock_assignment_ids: (employeeForm.livestock_assignment_ids || []).map(Number),
            } : {}),
        };
        try {
            if (editingEmployeeId) {
                await workforceService.updateEmployee(editingEmployeeId, payload);
                notification.success("Employee profile updated.", "Employee Updated");
            } else {
                await workforceService.createEmployee(payload);
                notification.success(
                    employeeForm.create_login_account
                        ? "Employee profile and login account created."
                        : "Employee profile created without a login account.",
                    "Employee Added"
                );
            }
            closeEmployeeModal();
            await load();
        } catch (err) {
            notification.error(err?.message || `Unable to ${editingEmployeeId ? "update" : "create"} employee.`, "Employee Error");
        }
    };

    const openEmployeeStatusAction = (employee) => {
        const nextStatus = employee.employment_status === "Active" ? "Inactive" : "Active";
        setEmployeeAction({ type: "status", employee, nextStatus });
    };

    const openArchiveEmployee = (employee) => {
        setArchiveReason("");
        setEmployeeAction({ type: "archive", employee });
    };

    const openRestoreEmployee = (employee) => {
        setEmployeeAction({ type: "restore", employee });
    };

    const performEmployeeAction = async () => {
        if (!employeeAction?.employee) return;
        const { type, employee, nextStatus } = employeeAction;
        try {
            if (type === "status") {
                await workforceService.setEmployeeStatus(employee.id, nextStatus);
                notification.success(`${employee.full_name} is now ${nextStatus.toLowerCase()}.`, "Employee Status");
            } else if (type === "archive") {
                if (!archiveReason.trim()) throw new Error("An archive reason is required.");
                await workforceService.archiveEmployee(employee.id, archiveReason.trim());
                notification.success(`${employee.full_name} moved to Archives.`, "Employee Archived");
            } else if (type === "restore") {
                await workforceService.restoreEmployee(employee.id);
                notification.success(`${employee.full_name} restored as inactive. Activate the employee when ready for assignments.`, "Employee Restored");
            }
            closeEmployeeActionModal();
            await refreshAll();
        } catch (err) {
            notification.error(err?.message || "Unable to update employee.", "Employee Error");
        }
    };

    const changePrimaryPosition = (value) => {
        setEmployeeForm((current) => ({
            ...current,
            primary_position_id: value,
            additional_position_ids: current.additional_position_ids.filter((id) => id !== String(value)),
        }));
    };

    const toggleAdditionalPosition = (positionId) => {
        const id = String(positionId);
        setEmployeeForm((current) => {
            if (id === String(current.primary_position_id)) return current;
            if (current.additional_position_ids.includes(id)) {
                return { ...current, additional_position_ids: current.additional_position_ids.filter((item) => item !== id) };
            }
            if (current.additional_position_ids.length >= 4) {
                notification.error("Maximum reached: 1 primary position plus 4 additional positions.", "Employee Position");
                return current;
            }
            return { ...current, additional_position_ids: [...current.additional_position_ids, id] };
        });
    };

    useEffect(() => {
        setTab(navigation.tab);
        setNavigationReturnTo(navigation.returnTo);
        if (navigation.tab === "tasks") {
            if (navigation.taskId) {
                setTaskSearch("");
                setTaskStatusFilter("All");
                setTaskPriorityFilter("All");
                setTaskEmployeeFilter("All");
                setTaskScheduleFilter("All");
                setTaskDateFilter("");
                setTaskReassignmentFilter(navigation.assignmentState);
            } else {
                if (navigation.date) {
                    setTaskDateFilter(navigation.date);
                    setTaskScheduleFilter("All");
                }
                if (navigation.employeeId) setTaskEmployeeFilter(navigation.employeeId);
                if (navigation.assignmentState !== "All") setTaskReassignmentFilter(navigation.assignmentState);
            }
            setFocusedTaskId(navigation.taskId);
        }
        if (navigation.tab === "employees") setFocusedEmployeeId(navigation.employeeId);
        if (navigation.tab === "leave") setFocusedLeaveRequestId(navigation.leaveRequestId);
    }, [navigation]);

    useEffect(() => {
        if (tab !== "employees" || !focusedEmployeeId || !employees.length) return;
        const focusKey = `${focusedEmployeeId}:${navigation.action || "view"}`;
        if (deepLinkEmployeeOpenedRef.current === focusKey) return;
        const employee = employees.find((item) => String(item.id) === String(focusedEmployeeId));
        if (!employee) return;
        deepLinkEmployeeOpenedRef.current = focusKey;
        if (navigation.action === "work-schedule") {
            setScheduleEffectiveDate(navigation.scheduleDate);
            setScheduleEmployee(employee);
        } else {
            openViewEmployee(employee);
        }
    }, [tab, focusedEmployeeId, employees, navigation.action, navigation.scheduleDate]);

    useEffect(() => {
        if (tab !== "tasks" || !focusedTaskId || loading) return;
        const timer = window.setTimeout(() => {
            const row = document.getElementById(`task-row-${focusedTaskId}`);
            row?.scrollIntoView({ behavior: "smooth", block: "center" });
            row?.focus?.({ preventScroll: true });
        }, 30);
        return () => window.clearTimeout(timer);
    }, [tab, focusedTaskId, loading, visibleTasks]);

    useEffect(() => {
        if (navigation.action !== "assisted-submission") {
            deepLinkAssistedOpenedRef.current = "";
            return;
        }
        const focusKey = `${navigation.taskId}:${navigation.action}`;
        if (
            tab !== "tasks"
            || !focusedTaskId
            || focusedTaskId !== navigation.taskId
            || loading
            || assistedTask
            || deepLinkAssistedOpenedRef.current === focusKey
        ) return;
        const task = tasks.find((item) => String(item.id) === String(focusedTaskId))
            || (String(focusedTaskRecord?.id) === String(focusedTaskId) ? focusedTaskRecord : null);
        if (
            !task
            || !REASSIGNABLE_TASK_STATUSES.has(task.status)
            || task.activity_date > today()
            || task.work_suspended
            || task.needs_reassignment
            || !task.assigned_employee_id
        ) return;
        // Closing clears modal state before the router finishes replacing the
        // URL. Consume the action first so that render cannot reopen the form.
        deepLinkAssistedOpenedRef.current = focusKey;
        openAssistedSubmission(task);
    }, [tab, navigation.action, navigation.taskId, focusedTaskId, loading, tasks, assistedTask, focusedTaskRecord]);

    return (
        <div className="workforce-layout">
            <Sidebar />
            <main className="workforce-page">
                <header className="workforce-header">
                    <div className="workforce-heading">
                        <h1>Task Management</h1>
                        <p>Assign work, review leave requests and coverage, monitor progress, and manage care plans.</p>
                    </div>
                    <div className="workforce-actions">
                        <AppHeaderActions />
                    </div>
                </header>
                {navigationReturnTo && (
                    <div className="task-management-calendar-return">
                        <button type="button" className="workforce-button secondary" onClick={() => router.push(navigationReturnTo)}>
                            <span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>
                            {navigation.fromDashboard ? "Back to Dashboard" : navigation.fromCrops ? "Back to Crops" : "Back to Staff Calendar"}
                        </button>
                        <span>{navigation.fromDashboard ? "Return to the Dashboard after reviewing this exact task." : navigation.fromCrops ? "Return to the crop harvest form after resolving this exact task." : "Return to the same calendar view, date, and filters."}</span>
                    </div>
                )}
                {error && <div className="workforce-error">{error} <button type="button" className="workforce-button secondary compact" onClick={load}>Retry</button></div>}
                <TaskManagementTabs
                    activeTab={tab}
                    canManageCareProtocols={canManageCareProtocols}
                    canManageLeaveRequests={canManageLeaveRequests}
                    onChange={setTab}
                />

                {tab === "tasks" && <>
                    <TaskSummaryCards stats={stats} />
                    <AssignmentsPanel
                        allEmployeesById={allEmployeesById}
                        filteredTasks={filteredTasks}
                        filterProps={{
                            employees,
                            filtersAreDefault: taskFiltersAreDefault,
                            onClear: clearTaskFilters,
                            onClearDate: () => {
                                setTaskDateFilter("");
                                setFocusedTaskId("");
                                setTaskScheduleFilter("Actionable Now");
                            },
                            priority: taskPriorityFilter,
                            priorityOptions: taskPriorityOptions,
                            reassignment: taskReassignmentFilter,
                            schedule: taskScheduleFilter,
                            search: taskSearch,
                            selectedDate: taskDateFilter,
                            selectedEmployee: taskEmployeeFilter,
                            setPriority: setTaskPriorityFilter,
                            setReassignment: setTaskReassignmentFilter,
                            setSchedule: setTaskScheduleFilter,
                            setSearch: setTaskSearch,
                            setSelectedEmployee: setTaskEmployeeFilter,
                            setStatus: (nextStatus) => {
                                setTaskStatusFilter(nextStatus);
                                if (HISTORICAL_TASK_STATUSES.has(nextStatus)) {
                                    setTaskScheduleFilter("All Scheduled");
                                }
                            },
                            status: taskStatusFilter,
                            statusOptions: taskStatusOptions,
                        }}
                        focusedTaskId={focusedTaskId}
                        loading={loading}
                        onAssignTask={() => setShowTaskForm(true)}
                        onCorrectUsage={(task) => openAssistedSubmission(task, true)}
                        onLoadMore={loadMore}
                        onOpenReview={openReviewSubmission}
                        onReassign={reassign}
                        onRecordWork={openAssistedSubmission}
                        onRefresh={handleManualRefresh}
                        onVoidUsage={voidCompletedTask}
                        refreshing={refreshing}
                        stats={stats}
                        tasks={tasks}
                        taskTotal={taskTotal}
                        visibleTasks={visibleTasks}
                    />
                </>}

                {tab === "employees" && (
                    <EmployeesPanel
                        employees={employees}
                        loading={loading}
                        onAdd={openAddEmployee}
                        onArchive={openArchiveEmployee}
                        onEdit={openEditEmployee}
                        onSchedule={(employee) => { setScheduleEffectiveDate(""); setScheduleEmployee(employee); }}
                        onStatusAction={openEmployeeStatusAction}
                        onView={openViewEmployee}
                        repairAccountLinks={repairEmployeeAccountLinks}
                        repairingAccountLinks={repairingAccountLinks}
                    />
                )}

                {tab === "archives" && (
                    <ArchiveRecords module="Employee" moduleOptions={["Employee", "Task"]} />
                )}
                {canManageLeaveRequests && tab === "leave" && (
                    <LeaveRequestsPanel employees={employees} onChanged={load} initialLeaveRequestId={focusedLeaveRequestId} onDismissDeepLink={dismissLeaveDeepLink} />
                )}

                {canManageCareProtocols && tab === "templates" && <CareProtocolManager />}
            </main>

            {scheduleEmployee && (
                <EmployeeWorkScheduleModal
                    employee={scheduleEmployee}
                    employees={employees}
                    effectiveDate={scheduleEffectiveDate}
                    onClose={closeWorkSchedule}
                    onSaved={load}
                />
            )}

            <WorkSubmissionReviewModal
                open={Boolean(reviewModalTaskId)}
                report={reviewReport}
                loading={reviewLoading}
                loadError={reviewLoadError}
                actionError={reviewActionError}
                processingAction={reviewProcessingAction}
                onClose={closeReviewModal}
                onRetry={() => loadReviewReport(reviewModalTaskId)}
                onApprove={(feedback, options) => performReviewAction("Approve", feedback, options)}
                onReturn={(feedback) => performReviewAction("Return", feedback)}
            />

            <TaskManagementModals
                {...{
                    archiveReason,
                    assistedCorrectionMode,
                    assistedEmployeeOptions,
                    assistedForm,
                    assistedIsCropHarvest,
                    assistedResourceItems,
                    assistedSaving,
                    assistedSelectedInventoryItem,
                    assistedTask,
                    changePrimaryPosition,
                    closeAssistedModal,
                    closeEmployeeActionModal,
                    closeEmployeeModal,
                    closeReassignModal,
                    closeTaskModal,
                    closeViewEmployeeModal,
                    editingEmployeeId,
                    employeeAction,
                    employeeAssignmentOptions,
                    employeeAssignmentsLoaded,
                    employeeAssignmentsLoading,
                    employeeForm,
                    employees,
                    filteredPositionGroups,
                    inventoryItems,
                    manualTaskResourceItems,
                    openEditEmployee,
                    otherReassignCandidates,
                    performEmployeeAction,
                    performTaskReassignment,
                    positionGroups,
                    positionSearch,
                    reassignCandidates,
                    reassignEmployeeId,
                    reassignProfile,
                    reassignSaving,
                    reassignSearch,
                    reassignTask,
                    recommendedReassignCandidates,
                    saveEmployeeProfile,
                    saveTask,
                    selectedAdditionalPositions,
                    selectedPrimaryPosition,
                    selectedTaskInventoryItem,
                    setArchiveReason,
                    setAssistedForm,
                    setEmployeeForm,
                    setPositionSearch,
                    setReassignEmployeeId,
                    setReassignSearch,
                    setTaskForm,
                    showEmployeeForm,
                    showTaskForm,
                    submitAssistedWork,
                    taskAssignmentStockError,
                    taskForm,
                    taskSaving,
                    existingTaskId,
                    taskSourceOptions,
                    tasks,
                    toggleAdditionalPosition,
                    toggleEmployeeWorkAssignment,
                    viewEmployee,
                    viewEmployeeAssignments,
                    viewEmployeeLoading,
                    viewEmployeeTasks,
                }}
            />
        </div>
    );
}

export default TaskManagement;
