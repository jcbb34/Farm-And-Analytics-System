"use client";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";

import { useVoidAuthorization } from "../../context/VoidAuthorizationContext.jsx";

import { MonitoringObservationFields, ObservationSummary, initialObservation, observationPayload, validateObservation } from "../../components/Monitoring/Monitoring.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FarmEventNotices } from "../../components/FarmEvents/FarmEvents.jsx";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { workforceService } from "../../services/workforceService.js";
import { buildMyTasksPageQuery } from "./taskPageQuery.js";
import { attendanceStatusForSchedule } from "../../utils/attendanceSchedule.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../../services/idempotencyKey.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import SharedDeviceTasks from "../../components/SharedDevice/SharedDeviceTasks.jsx";
import EvidencePhotoField, { EvidenceViewButton } from "../../components/EvidencePhoto/EvidencePhoto.jsx";
import {
    DEFAULT_FARM_TIMEZONE,
    addCalendarDays,
    dateKeysBetween,
    farmDateKey,
    formatDateKey,
    startOfWeekKey,
} from "../../utils/farmCalendar.js";
import {
    DEFAULT_SCHEDULE_FILTER,
    DEFAULT_TASK_VIEW,
    TASK_VIEW_OPTIONS,
    apiViewForTaskView,
    canWorkTaskForView,
    filterAndSortMyTasks,
    isFutureTaskForView,
    scheduleForTaskViewChange,
} from "./taskView.js";
import {
    DEFAULT_MY_TASKS_TAB,
    normalizeMyTasksTab,
    searchWithMyTasksTab,
    tabFromSearch,
} from "./tabState.js";
import {
    SHARED_DEVICE_STORAGE_KEY,
    isSharedModeRequested,
    searchWithSharedMode,
} from "./sharedDeviceMode.js";
import "./MyTasks.css";

const statusClass = (value) => String(value || "").toLowerCase().replaceAll(" ", "-");

const CLOSED_TASK_STATUSES = new Set(["Completed", "Approved", "Cancelled", "Resolved", "Voided"]);
const MISSED_TASK_STATUSES = new Set(["Pending", "In Progress", "Returned"]);
const READ_ONLY_TASK_STATUSES = new Set(["Completed", "Approved", "Cancelled", "Resolved", "Voided"]);

const DEEP_LINK_TASK_VIEWS = new Set([
    "active", "pending", "in-progress", "returned", "review", "completed", "history", "all",
]);

function myTasksDeepLinkState() {
    if (typeof window === "undefined") return { taskId: "", view: DEFAULT_TASK_VIEW, returnTo: "" };
    const params = new URLSearchParams(window.location.search);
    const taskId = /^\d+$/.test(params.get("taskId") || "") ? params.get("taskId") : "";
    const requestedView = params.get("view") || DEFAULT_TASK_VIEW;
    const view = DEEP_LINK_TASK_VIEWS.has(requestedView) ? requestedView : DEFAULT_TASK_VIEW;
    const rawReturn = params.get("returnTo") || "";
    const returnTo = rawReturn === "/dashboard" || rawReturn.startsWith("/dashboard?") || rawReturn.startsWith("/dashboard#")
        ? rawReturn
        : "";
    return { taskId, view, returnTo };
}

function isMissedTask(task, todayKey) {
    return Boolean(!task?.work_suspended && task?.activity_date && task.activity_date < todayKey && MISSED_TASK_STATUSES.has(task.status));
}

function daysOverdue(task, todayKey) {
    if (!isMissedTask(task, todayKey)) return 0;
    const [y1, m1, d1] = String(task.activity_date).split("-").map(Number);
    const [y2, m2, d2] = String(todayKey).split("-").map(Number);
    return Math.max(1, Math.round((new Date(y2, m2 - 1, d2) - new Date(y1, m1 - 1, d1)) / 86400000));
}

function attendanceTime(value) {
    if (!value) return "Not recorded";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" });
}

function shiftTime(value) {
    if (!value) return null;
    const [hour, minute] = String(value).split(":").map(Number);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return String(value);
    return new Date(2000, 0, 1, hour, minute).toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" });
}

function MyTasks() {
    const requestVoid = useVoidAuthorization();
    const notification = useNotification();
    const { user, logout } = useAuth();
    const [sharedDeviceMode, setSharedDeviceMode] = useState(() => {
        if (typeof window === "undefined") return false;
        try {
            return isSharedModeRequested(window.location.search)
                || localStorage.getItem(SHARED_DEVICE_STORAGE_KEY) === "1";
        } catch {
            return isSharedModeRequested(window.location.search);
        }
    });
    const [activeTab, setActiveTab] = useState(() => (
        typeof window === "undefined" ? DEFAULT_MY_TASKS_TAB : tabFromSearch(window.location.search)
    ));
    const initialDeepLink = useMemo(() => myTasksDeepLinkState(), []);
    const [focusedTaskId, setFocusedTaskId] = useState(initialDeepLink.taskId);
    const [dashboardReturnTo, setDashboardReturnTo] = useState(initialDeepLink.returnTo);
    const [tasks, setTasks] = useState([]);
    const [expandedTaskIds, setExpandedTaskIds] = useState(() => new Set());
    const [taskTotal, setTaskTotal] = useState(0);
    const [activeTaskSnapshot, setActiveTaskSnapshot] = useState([]);
    const taskCacheRef = useRef(new Map());
    const taskRequestRef = useRef(null);
    const taskSummaryRequestRef = useRef(null);
    const identityKey = useMemo(
        () => String(user?.id ?? user?.userCode ?? user?.username ?? "anonymous"),
        [user?.id, user?.userCode, user?.username],
    );
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [taskSummary, setTaskSummary] = useState(null);
    const [submitId, setSubmitId] = useState(null);
    const [reportId, setReportId] = useState(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [loadingMore, setLoadingMore] = useState(false);
    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(searchTerm), 300);
        return () => window.clearTimeout(timer);
    }, [searchTerm]);
    const [taskView, setTaskView] = useState(initialDeepLink.view);
    const [priorityFilter, setPriorityFilter] = useState("all");
    const [scheduleFilter, setScheduleFilter] = useState(initialDeepLink.taskId ? "all" : DEFAULT_SCHEDULE_FILTER);
    const [selectedTaskDate, setSelectedTaskDate] = useState(null);
    const [form, setForm] = useState({ actual_quantity: "", actual_unit: "", harvest_type_intent: "", evidence_url: "", worker_notes: "", problem_report: "" });
    const [submitting, setSubmitting] = useState(false);
    const submitRequestRef = useRef(null);
    const [farmTimezone, setFarmTimezone] = useState(DEFAULT_FARM_TIMEZONE);
    const [farmToday, setFarmToday] = useState(() => farmDateKey(new Date(), DEFAULT_FARM_TIMEZONE));
    const [scheduleWeekStart, setScheduleWeekStart] = useState(() => startOfWeekKey(farmDateKey(new Date(), DEFAULT_FARM_TIMEZONE)));
    const [scheduleData, setScheduleData] = useState({ tasks: [], attendance: [], leave: [], shifts: [], availability: [] });
    const [scheduleLoadedRange, setScheduleLoadedRange] = useState("");
    const [scheduleLoading, setScheduleLoading] = useState(false);
    const [scheduleError, setScheduleError] = useState("");
    const [leaveRequest, setLeaveRequest] = useState(() => {
        const tomorrow = addCalendarDays(farmDateKey(new Date(), DEFAULT_FARM_TIMEZONE), 1);
        return { leave_type: "Vacation Leave", start_date: tomorrow, end_date: tomorrow, reason: "" };
    });
    const [leaveSubmitting, setLeaveSubmitting] = useState(false);
    const [myLeaveRequests, setMyLeaveRequests] = useState([]);
    const [leaveLoaded, setLeaveLoaded] = useState(false);
    const [leaveLoading, setLeaveLoading] = useState(false);
    const [leaveError, setLeaveError] = useState("");
    const [todayAttendance, setTodayAttendance] = useState(null);
    const [todayAttendanceAvailability, setTodayAttendanceAvailability] = useState(null);
    const [attendanceLoading, setAttendanceLoading] = useState(false);
    const [attendanceAction, setAttendanceAction] = useState("");
    const [attendanceError, setAttendanceError] = useState("");

    const loadTodayAttendance = useCallback(async () => {
        setAttendanceLoading(true);
        setAttendanceError("");
        try {
            const [attendance, schedule] = await Promise.all([
                workforceService.getMyAttendanceToday(),
                workforceService.getMySchedule(farmToday, farmToday),
            ]);
            setTodayAttendance(attendance || null);
            setTodayAttendanceAvailability((schedule?.availability || [])[0] || null);
        } catch (err) {
            setAttendanceError(err?.message || "Unable to load today's attendance.");
        } finally {
            setAttendanceLoading(false);
        }
    }, [farmToday]);

    const submitAttendanceAction = useCallback(async (action) => {
        if (attendanceAction) return;
        setAttendanceAction(action);
        setAttendanceError("");
        try {
            const result = action === "check-in"
                ? await workforceService.checkIn()
                : await workforceService.checkOut();
            setTodayAttendance(result || null);
            notification.success(
                action === "check-in" ? "Check In recorded using farm server time." : "Check Out recorded using farm server time.",
                "Attendance Recorded",
            );
            await loadTodayAttendance();
        } catch (err) {
            const message = err?.message || "Unable to record attendance.";
            setAttendanceError(message);
            notification.error(message, "Attendance Error");
        } finally {
            setAttendanceAction("");
        }
    }, [attendanceAction, loadTodayAttendance, notification]);

    useEffect(() => {
        if (!sharedDeviceMode) loadTodayAttendance();
    }, [identityKey, farmToday, sharedDeviceMode, loadTodayAttendance]);

    const backendTaskView = useMemo(() => apiViewForTaskView(taskView), [taskView]);
    const backendTaskScope = useMemo(() => {
        if (backendTaskView !== "active") return "all";
        if (scheduleFilter === "all") return "all";
        if (scheduleFilter === "date" && selectedTaskDate && selectedTaskDate > addCalendarDays(farmToday, 7)) return "all";
        return "timeline";
    }, [backendTaskView, scheduleFilter, selectedTaskDate, farmToday]);

    const changeTab = useCallback((requestedTab, { replace = false } = {}) => {
        const nextTab = normalizeMyTasksTab(requestedTab);
        setActiveTab(nextTab);
        if (typeof window === "undefined") return;
        const nextSearch = searchWithMyTasksTab(window.location.search, nextTab);
        const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash || ""}`;
        window.history[replace ? "replaceState" : "pushState"]({}, "", nextUrl);
    }, []);

    useEffect(() => {
        // This reset must run before the task-loading effect when identity changes.
        // Placing this after the loader immediately
        // aborted the first My Tasks request and could leave the spinner active.
        taskRequestRef.current?.abort();
        taskSummaryRequestRef.current?.abort();
        taskRequestRef.current = null;
        taskSummaryRequestRef.current = null;
        taskCacheRef.current.clear();
        setTasks([]);
        setExpandedTaskIds(new Set());
        setTaskTotal(0);
        setActiveTaskSnapshot([]);
        setTaskSummary(null);
        setLoading(false);
        setError("");
        setScheduleLoadedRange("");
        setLeaveLoaded(false);
        return () => {
            taskRequestRef.current?.abort();
            taskSummaryRequestRef.current?.abort();
        };
    }, [identityKey]);

    useEffect(() => {
        if (typeof window === "undefined") return undefined;
        const requested = new URLSearchParams(window.location.search).get("tab");
        const normalized = normalizeMyTasksTab(requested);
        if (requested !== normalized) changeTab(normalized, { replace: true });
        const onPopState = () => {
            setActiveTab(tabFromSearch(window.location.search));
            const deepLink = myTasksDeepLinkState();
            setFocusedTaskId(deepLink.taskId);
            setDashboardReturnTo(deepLink.returnTo);
            if (deepLink.taskId) {
                setTaskView(deepLink.view);
                setScheduleFilter("all");
                setPriorityFilter("all");
                setSearchTerm("");
                setSelectedTaskDate(null);
            }
            try {
                setSharedDeviceMode(
                    isSharedModeRequested(window.location.search)
                    || localStorage.getItem(SHARED_DEVICE_STORAGE_KEY) === "1",
                );
            } catch {
                setSharedDeviceMode(isSharedModeRequested(window.location.search));
            }
        };
        window.addEventListener("popstate", onPopState);
        return () => window.removeEventListener("popstate", onPopState);
    }, [changeTab]);

    const loadTasks = useCallback(async (view = "active", { force = false, sharedDevice = false, scope = "all" } = {}) => {
        const query = buildMyTasksPageQuery({
            view, scope, taskView: sharedDevice ? "active" : taskView,
            search: sharedDevice ? "" : debouncedSearch, priorityFilter: sharedDevice ? "all" : priorityFilter,
            scheduleFilter: sharedDevice ? "timeline" : scheduleFilter,
            selectedTaskDate, todayKey: farmToday, upcomingLimitKey: addCalendarDays(farmToday, 7),
            sharedDevice,
        });
        const cacheKey = `${identityKey}:${JSON.stringify(query)}`;
        if (!force && taskCacheRef.current.has(cacheKey)) {
            const cached = taskCacheRef.current.get(cacheKey);
            setTasks(cached.items);
            setTaskTotal(cached.total);
            if (view === "active") setActiveTaskSnapshot(cached.items);
            return cached.items;
        }

        taskRequestRef.current?.abort();
        const controller = new AbortController();
        taskRequestRef.current = controller;
        setLoading(true);
        setError("");
        try {
            const page = await workforceService.getMyTasksPage(query, { signal: controller.signal });
            if (controller.signal.aborted) return [];
            const rows = page?.items || [];
            taskCacheRef.current.set(cacheKey, { items: rows, total: page?.total || 0 });
            setTasks(rows);
            setTaskTotal(page?.total || 0);
            if (view === "active") setActiveTaskSnapshot(rows);
            return rows;
        } catch (err) {
            if (controller.signal.aborted) return [];
            setError(err?.message || "Unable to load your tasks.");
            return [];
        } finally {
            if (taskRequestRef.current === controller) {
                taskRequestRef.current = null;
                setLoading(false);
            }
        }
    }, [identityKey, taskView, debouncedSearch, priorityFilter, scheduleFilter, selectedTaskDate, farmToday]);

    const loadMoreTasks = useCallback(async () => {
        if (loadingMore || tasks.length >= taskTotal) return;
        setLoadingMore(true);
        const controller = new AbortController();
        taskRequestRef.current = controller;
        try {
            const query = buildMyTasksPageQuery({
                view: backendTaskView, scope: backendTaskScope, taskView,
                search: debouncedSearch, priorityFilter, scheduleFilter, selectedTaskDate,
                todayKey: farmToday, upcomingLimitKey: addCalendarDays(farmToday, 7),
                sharedDevice: sharedDeviceMode,
            });
            const page = await workforceService.getMyTasksPage({ ...query, offset: tasks.length }, { signal: controller.signal });
            if (controller.signal.aborted) return;
            setTasks((current) => [...current, ...(page?.items || [])]);
            setTaskTotal(page?.total || 0);
        } catch (err) {
            if (!controller.signal.aborted) setError(err?.message || "Unable to load more tasks.");
        } finally {
            if (taskRequestRef.current === controller) taskRequestRef.current = null;
            setLoadingMore(false);
        }
    }, [loadingMore, tasks.length, taskTotal, backendTaskView, backendTaskScope, taskView,
        debouncedSearch, priorityFilter, scheduleFilter, selectedTaskDate, farmToday, sharedDeviceMode]);

    const loadTaskSummary = useCallback(async () => {
        taskSummaryRequestRef.current?.abort();
        const controller = new AbortController();
        taskSummaryRequestRef.current = controller;
        try {
            const summary = await workforceService.getMyTaskSummary({ signal: controller.signal });
            if (!controller.signal.aborted) setTaskSummary(summary || null);
        } catch {
            // The task list remains usable if summary counts fail; fall back to
            // the currently loaded timeline counts instead of blocking rendering.
        } finally {
            if (taskSummaryRequestRef.current === controller) taskSummaryRequestRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (activeTab !== "tasks") return;
        if (sharedDeviceMode && backendTaskView !== "active") return;
        loadTasks(backendTaskView, { force: false, sharedDevice: sharedDeviceMode, scope: backendTaskScope });
        if (!sharedDeviceMode) loadTaskSummary();
    }, [activeTab, backendTaskView, backendTaskScope, loadTaskSummary, loadTasks, sharedDeviceMode]);

    useEffect(() => {
        if (!sharedDeviceMode) return;
        setActiveTab("tasks");
        setTaskView(DEFAULT_TASK_VIEW);
        setScheduleFilter(DEFAULT_SCHEDULE_FILTER);
        setSelectedTaskDate(null);
        if (typeof window !== "undefined") {
            const nextSearch = searchWithSharedMode(window.location.search, true);
            const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash || ""}`;
            window.history.replaceState({}, "", nextUrl);
        }
        // The task-loading effect above will fetch the privacy-minimized
        // shared-device response after these task defaults are applied.
        setTasks([]);
        setActiveTaskSnapshot([]);
    }, [sharedDeviceMode]);

    const minimumLeaveDate = addCalendarDays(farmToday, 1);
    const leaveReasonRequired = leaveRequest.leave_type === "Other";

    const applyFarmCalendar = useCallback((config, resetWeek = false) => {
        if (!config) return;
        const timezone = config.timezone || DEFAULT_FARM_TIMEZONE;
        const today = config.today || farmDateKey(new Date(), timezone);
        const tomorrow = addCalendarDays(today, 1);
        setFarmTimezone(timezone);
        setFarmToday(today);
        if (resetWeek) setScheduleWeekStart(startOfWeekKey(today));
        setLeaveRequest((current) => {
            const start = !current.start_date || current.start_date < tomorrow ? tomorrow : current.start_date;
            const end = !current.end_date || current.end_date < start ? start : current.end_date;
            return { ...current, start_date: start, end_date: end };
        });
    }, []);

    useEffect(() => {
        let cancelled = false;
        workforceService.getCalendarConfig().then((config) => {
            if (!cancelled) applyFarmCalendar(config, true);
        }).catch(() => {});
        return () => { cancelled = true; };
    }, [applyFarmCalendar]);

    useEffect(() => {
        if (activeTab !== "leave") return undefined;
        let cancelled = false;
        const refreshDate = () => {
            if (document.visibilityState === "hidden") return;
            workforceService.getCalendarConfig().then((config) => {
                if (!cancelled) applyFarmCalendar(config);
            }).catch(() => {});
        };
        // Refresh the server's farm date when returning to the form and while
        // it stays open across midnight. The backend remains authoritative.
        refreshDate();
        window.addEventListener("focus", refreshDate);
        document.addEventListener("visibilitychange", refreshDate);
        const timer = window.setInterval(refreshDate, 60000);
        return () => {
            cancelled = true;
            window.clearInterval(timer);
            window.removeEventListener("focus", refreshDate);
            document.removeEventListener("visibilitychange", refreshDate);
        };
    }, [activeTab, applyFarmCalendar]);

    const scheduleWeekEnd = useMemo(() => addCalendarDays(scheduleWeekStart, 6), [scheduleWeekStart]);
    const scheduleRangeKey = `${scheduleWeekStart}:${scheduleWeekEnd}`;

    const refreshMySchedule = useCallback(async () => {
        setScheduleLoading(true);
        setScheduleError("");
        try {
            const payload = await workforceService.getMySchedule(scheduleWeekStart, scheduleWeekEnd);
            setScheduleData(payload || { tasks: [], attendance: [], leave: [], shifts: [] });
            setScheduleLoadedRange(`${scheduleWeekStart}:${scheduleWeekEnd}`);
        } catch (err) {
            setScheduleError(err?.message || "Unable to load your schedule.");
        } finally {
            setScheduleLoading(false);
        }
    }, [scheduleWeekStart, scheduleWeekEnd]);

    useEffect(() => {
        if (activeTab === "schedule" && scheduleLoadedRange !== scheduleRangeKey) refreshMySchedule();
    }, [activeTab, refreshMySchedule, scheduleLoadedRange, scheduleRangeKey]);

    const refreshMyLeaveRequests = useCallback(async () => {
        setLeaveLoading(true);
        setLeaveError("");
        try {
            setMyLeaveRequests(await workforceService.getMyLeave() || []);
            setLeaveLoaded(true);
        } catch (err) {
            setLeaveError(err?.message || "Unable to load your leave requests.");
        } finally {
            setLeaveLoading(false);
        }
    }, []);

    useEffect(() => {
        if (activeTab === "leave" && !leaveLoaded) refreshMyLeaveRequests();
    }, [activeTab, leaveLoaded, refreshMyLeaveRequests]);

    const submitLeaveRequest = async (event) => {
        event.preventDefault();
        if (leaveSubmitting) return;
        if (!leaveRequest.start_date || !leaveRequest.end_date || leaveRequest.end_date < leaveRequest.start_date) {
            notification.error("Choose a valid leave date range.", "Leave Request");
            return;
        }
        if (leaveRequest.start_date < minimumLeaveDate || leaveRequest.end_date < minimumLeaveDate) {
            notification.error("Leave start and end dates must be tomorrow or later in the farm timezone.", "Leave Request");
            return;
        }
        const reason = String(leaveRequest.reason || "").trim();
        if (leaveReasonRequired && !reason) {
            notification.error("Please enter a reason when the leave type is Other.", "Leave Request");
            return;
        }
        setLeaveSubmitting(true);
        try {
            await workforceService.requestMyLeave({
                leave_type: leaveRequest.leave_type,
                start_date: leaveRequest.start_date,
                end_date: leaveRequest.end_date,
                reason: reason || null,
            });
            notification.success("Leave request submitted for manager approval.", "Leave Request");
            setLeaveRequest((current) => ({ ...current, reason: "" }));
            setScheduleLoadedRange("");
            await refreshMyLeaveRequests();
        } catch (err) {
            const validationMessage = err?.status === 422 && Array.isArray(err?.response?.detail)
                ? err.response.detail.map((item) => item.msg).filter(Boolean).join(" ")
                : "";
            notification.error(validationMessage || err?.message || "Unable to submit leave request.", "Leave Request");
        } finally {
            setLeaveSubmitting(false);
        }
    };

    const cancelOwnLeave = async (leaveId) => {
        try {
            await workforceService.cancelLeave(leaveId);
            notification.success("Leave request cancelled. Task availability was recalculated.", "Leave Request");
            setScheduleLoadedRange("");
            await refreshMyLeaveRequests();
        } catch (err) {
            notification.error(err?.message || "Unable to cancel leave request.", "Leave Request");
        }
    };

    const todayKey = farmToday;
    const upcomingLimitKey = useMemo(() => addCalendarDays(todayKey, 7), [todayKey]);
    const summaryTasks = activeTaskSnapshot;

    const groups = useMemo(() => ({
        held: Number(taskSummary?.held ?? summaryTasks.filter((x) => x.work_suspended).length),
        total: Number(taskSummary?.total ?? summaryTasks.length),
        today: Number(taskSummary?.today ?? summaryTasks.filter((x) => x.activity_date === todayKey && !CLOSED_TASK_STATUSES.has(x.status)).length),
        missed: Number(taskSummary?.missed ?? summaryTasks.filter((x) => isMissedTask(x, todayKey)).length),
        progress: Number(taskSummary?.in_progress ?? summaryTasks.filter((x) => x.status === "In Progress").length),
        returned: Number(taskSummary?.returned ?? summaryTasks.filter((x) => x.status === "Returned").length),
        review: Number(taskSummary?.for_review ?? summaryTasks.filter((x) => x.status === "Submitted for Review").length),
        upcoming: Number(taskSummary?.upcoming ?? summaryTasks.filter((x) => x.activity_date > todayKey && x.activity_date <= upcomingLimitKey && !CLOSED_TASK_STATUSES.has(x.status)).length),
    }), [summaryTasks, taskSummary, todayKey, upcomingLimitKey]);

    const submitTask = useMemo(
        () => tasks.find((task) => Number(task.id) === Number(submitId)) || null,
        [tasks, submitId],
    );
    const reportTask = useMemo(
        () => tasks.find((task) => Number(task.id) === Number(reportId)) || null,
        [tasks, reportId],
    );
    const isCropHarvestSubmission = Boolean(
        submitTask?.source_module === "Crop" && submitTask?.source_type === "crop_harvest"
    );

    useEffect(() => {
        if (!submitTask && !reportTask) return undefined;
        const previousOverflow = document.body.style.overflow;
        const onKeyDown = (event) => {
            if (event.key === "Escape") {
                setSubmitId(null);
                setReportId(null);
            }
        };
        document.body.style.overflow = "hidden";
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [submitTask, reportTask]);

    const priorityOptions = useMemo(() => [...new Set(tasks.map((task) => task.priority).filter(Boolean))].sort(), [tasks]);

    const filteredTasks = useMemo(() => filterAndSortMyTasks({
        tasks,
        taskView,
        searchTerm,
        priorityFilter,
        scheduleFilter,
        selectedDateKey: selectedTaskDate,
        todayKey,
        upcomingLimitKey,
    }), [tasks, taskView, searchTerm, priorityFilter, scheduleFilter, selectedTaskDate, todayKey, upcomingLimitKey]);

    useEffect(() => {
        if (!focusedTaskId || loading || activeTab !== "tasks") return undefined;
        const target = filteredTasks.find((task) => String(task.id) === String(focusedTaskId));
        if (!target) return undefined;
        const timer = window.setTimeout(() => {
            const card = document.getElementById(`my-task-${focusedTaskId}`);
            card?.scrollIntoView({ behavior: "smooth", block: "center" });
            card?.focus?.({ preventScroll: true });
        }, 30);
        return () => window.clearTimeout(timer);
    }, [focusedTaskId, loading, activeTab, filteredTasks]);

    const filtersAreDefault = searchTerm === ""
        && taskView === DEFAULT_TASK_VIEW
        && priorityFilter === "all"
        && scheduleFilter === DEFAULT_SCHEDULE_FILTER
        && selectedTaskDate === null;

    const handleTaskViewChange = (event) => {
        const nextView = event.target.value;
        setScheduleFilter((current) => scheduleForTaskViewChange(taskView, nextView, current));
        setSelectedTaskDate(null);
        setTaskView(nextView);
    };

    const clearFilters = () => {
        setSearchTerm("");
        setTaskView(DEFAULT_TASK_VIEW);
        setPriorityFilter("all");
        setScheduleFilter(DEFAULT_SCHEDULE_FILTER);
        setSelectedTaskDate(null);
    };

    const applySummaryFilter = (kind) => {
        setSearchTerm("");
        setPriorityFilter("all");
        setSelectedTaskDate(null);
        if (kind === "total") {
            setTaskView("active");
            setScheduleFilter("all");
        } else if (kind === "progress") {
            setTaskView("in-progress");
            setScheduleFilter("timeline");
        } else if (kind === "returned") {
            setTaskView("returned");
            setScheduleFilter("timeline");
        } else if (kind === "review") {
            setTaskView("review");
            setScheduleFilter("timeline");
        } else {
            setTaskView("active");
            setScheduleFilter(kind === "today" ? "today" : kind === "missed" ? "overdue" : "upcoming");
        }
    };

    const openTasksForDate = (dateKey) => {
        setTaskView(DEFAULT_TASK_VIEW);
        setPriorityFilter("all");
        setSearchTerm("");
        setScheduleFilter("date");
        setSelectedTaskDate(dateKey);
        changeTab("tasks");
    };

    const refreshActiveTab = async () => {
        const refreshes = sharedDeviceMode ? [] : [loadTodayAttendance()];
        if (activeTab === "tasks") {
            taskCacheRef.current.clear();
            refreshes.push(
                loadTasks(backendTaskView, { force: true, sharedDevice: sharedDeviceMode, scope: backendTaskScope }),
                sharedDeviceMode ? Promise.resolve() : loadTaskSummary(),
            );
        } else if (activeTab === "schedule") {
            refreshes.push(refreshMySchedule());
        } else if (activeTab === "leave") {
            refreshes.push(refreshMyLeaveRequests());
        }
        await Promise.all(refreshes);
    };

    useFarmModuleUpdates(["my_tasks", "tasks", "calendar", "employees"], refreshActiveTab, { editing: Boolean(submitId || reportId) });

    const startTask = async (task) => {
        if (isFutureTaskForView(task, todayKey)) {
            notification.warning(`This task becomes available on ${formatDateKey(task.activity_date, { month: "short", day: "numeric", year: "numeric" })}.`, "Upcoming Task");
            return;
        }
        try {
            await workforceService.startTask(task.id);
            notification.success("Task started.", "My Tasks");
            taskCacheRef.current.clear();
            await loadTasks(backendTaskView, { force: true, sharedDevice: sharedDeviceMode, scope: backendTaskScope });
        } catch (err) {
            notification.error(err?.message || "Unable to start task.", "Task Error");
        }
    };

    const openSubmit = (task) => {
        if (isFutureTaskForView(task, todayKey)) {
            notification.warning(`This task becomes available on ${formatDateKey(task.activity_date, { month: "short", day: "numeric", year: "numeric" })}.`, "Upcoming Task");
            return;
        }
        clearStableIdempotencyKey(submitRequestRef);
        setSubmitId(task.id);
        const isCropHarvestTask = task.source_module === "Crop" && task.source_type === "crop_harvest";
        setForm({
            actual_quantity: task.latest_submission?.actual_quantity ?? (task.resource_required && task.planned_quantity != null ? task.planned_quantity : ""),
            actual_unit: isCropHarvestTask
                ? "kg"
                : task.resource_required
                    ? (task.planned_inventory_unit || task.planned_unit || "")
                    : (task.latest_submission?.actual_unit || ""),
            harvest_type_intent: isCropHarvestTask ? (task.latest_submission?.harvest_type_intent || "") : "",
            monitoring: task.latest_submission?.monitoring || initialObservation(task.monitoring_context),
            evidence_url: "", worker_notes: "", problem_report: "",
        });
    };

    const submit = async (event, task) => {
        event.preventDefault();
        if (isFutureTaskForView(task, todayKey)) {
            notification.warning(`This task becomes available on ${formatDateKey(task.activity_date, { month: "short", day: "numeric", year: "numeric" })}.`, "Upcoming Task");
            return;
        }
        if (task.requires_evidence && !String(form.evidence_url || "").trim()) {
            notification.error("Upload an evidence photo before submitting.", "Evidence Required");
            return;
        }
        if (task.source_module === "Crop" && task.source_type === "crop_harvest" && !form.harvest_type_intent) {
            notification.error("Choose Partial Harvest or Final Harvest before submitting for manager confirmation.", "Harvest Type Required");
            return;
        }
        const monitoringError = validateObservation(form.monitoring, task.monitoring_context);
        if (monitoringError) { notification.error(monitoringError, "Monitoring Observation"); return; }
        const payload = {
            monitoring: observationPayload(form.monitoring, task.monitoring_context),
            actual_quantity: form.actual_quantity === "" ? null : Number(form.actual_quantity),
            actual_unit: form.actual_unit || null,
            harvest_type_intent: task.source_module === "Crop" && task.source_type === "crop_harvest" ? form.harvest_type_intent : null,
            evidence_url: form.evidence_url || null,
            worker_notes: form.worker_notes || null,
            problem_report: form.problem_report || null,
        };
        const idempotencyKey = stableIdempotencyKey(submitRequestRef, payload, `task-submit:${task.id}`);
        setSubmitting(true);
        try {
            const updatedTask = await workforceService.submitTask(task.id, payload, idempotencyKey);
            clearStableIdempotencyKey(submitRequestRef);
            setTasks((current) => current.map((item) => Number(item.id) === Number(updatedTask?.id) ? updatedTask : item));
            notification.success(
                updatedTask?.status === "Submitted for Review"
                    ? (task.resource_required
                        ? "Work submitted for manager review. The reported inventory quantity is reserved and will be deducted only if approved."
                        : "Work submitted for manager review.")
                    : updatedTask?.status === "Completed"
                        ? "Work recorded and completed."
                        : `Work submitted. Current status: ${updatedTask?.status || "Updated"}.`,
                "Task Submitted",
            );
            setSubmitId(null);
            taskCacheRef.current.clear();
            await loadTasks(backendTaskView, { force: true, sharedDevice: sharedDeviceMode, scope: backendTaskScope });
        } catch (err) {
            notification.error(err?.message || "Unable to submit task.", "Submission Error");
        } finally {
            setSubmitting(false);
        }
    };

    const refreshSharedTasks = useCallback(async () => {
        taskCacheRef.current.delete("shared:active");
        return loadTasks("active", { force: true, sharedDevice: true, scope: "timeline" });
    }, [loadTasks]);

    const updateSharedTask = useCallback((updatedTask) => {
        if (!updatedTask?.id) return;
        const replace = (rows) => rows.map((item) => Number(item.id) === Number(updatedTask.id) ? updatedTask : item);
        setTasks(replace);
        setActiveTaskSnapshot(replace);
        taskCacheRef.current.delete("shared:active");
    }, []);

    const enterSharedDeviceMode = useCallback(() => {
        try { localStorage.setItem(SHARED_DEVICE_STORAGE_KEY, "1"); } catch {}
        setSharedDeviceMode(true);
    }, []);

    const exitSharedDeviceMode = useCallback(() => {
        try { localStorage.removeItem(SHARED_DEVICE_STORAGE_KEY); } catch {}
        setSharedDeviceMode(false);
        if (typeof window !== "undefined") {
            const nextSearch = searchWithSharedMode(window.location.search, false);
            const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash || ""}`;
            window.history.replaceState({}, "", nextUrl);
        }
    }, []);

    const lockSharedDevice = useCallback(async (reason = "manual") => {
        const { serverReleased } = await logout({ forceLocal: true });
        if (typeof window !== "undefined") {
            const returnTo = "/my-tasks?tab=tasks&shared=1";
            const lockFlag = reason === "inactivity" ? "&locked=1" : "";
            const releaseFlag = serverReleased ? "" : "&releasePending=1";
            window.location.assign(`/login?from=${encodeURIComponent(returnTo)}${lockFlag}${releaseFlag}`);
        }
    }, [logout]);

    if (sharedDeviceMode) {
        return <SharedDeviceTasks
            tasks={tasks}
            loading={loading}
            error={error}
            todayKey={todayKey}
            user={user}
            onRefresh={refreshSharedTasks}
            onTaskUpdated={updateSharedTask}
            onExit={exitSharedDeviceMode}
            onLock={lockSharedDevice}
        />;
    }

    const tabs = [
        { id: "tasks", label: "Assigned Tasks", icon: "task_alt" },
        { id: "schedule", label: "My Schedule", icon: "calendar_month" },
        { id: "leave", label: "Leave Requests", icon: "event_busy" },
    ];

    return <div className="workforce-layout"><Sidebar/><main className="workforce-page my-tasks-page">
        <header className="workforce-header">
            <div className="workforce-heading">
                <h1>My Tasks</h1>
                <p>View assigned work first, then check your schedule or manage leave requests.</p>
            </div>
            <div className="workforce-actions"><button type="button" className="workforce-button secondary compact" onClick={enterSharedDeviceMode}><span className="material-symbols-outlined" aria-hidden="true">tablet_mac</span><span>Shared Device Mode</span></button><AppHeaderActions/></div>
        </header>

        {dashboardReturnTo && <div className="task-management-calendar-return my-tasks-dashboard-return">
            <button type="button" className="workforce-button secondary" onClick={() => window.location.assign(dashboardReturnTo)}>
                <span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>
                Back to Dashboard
            </button>
            <span>Return after viewing this exact assignment.</span>
        </div>}

        <section className="my-attendance-bar" aria-label="Today's Attendance">
            <div className="my-attendance-copy">
                <strong>Today's Attendance</strong>
                {attendanceLoading ? <span>Loading attendance…</span> : (() => {
                    const availability = todayAttendanceAvailability;
                    const currentAttendanceStatus = attendanceStatusForSchedule(todayAttendance, availability);
                    const start = shiftTime(availability?.start_time);
                    const end = shiftTime(availability?.end_time);
                    const scheduleLabel = start && end ? `${start}–${end}` : availability?.schedule_status === "Needs Setup" || availability?.status === "Schedule Needs Setup" ? "Schedule Needs Setup" : availability?.status || "Schedule not recorded";
                    if (availability?.status === "On Leave") return <span>{scheduleLabel} | Approved Leave</span>;
                    if (["Rest Day", "Special Day Off"].includes(availability?.status)) return <span>{scheduleLabel} | {availability.status}</span>;
                    if (!todayAttendance) return <span>Today: {scheduleLabel} | Not Checked In</span>;
                    if (todayAttendance.check_out_at) return <span>{scheduleLabel} | Checked in {attendanceTime(todayAttendance.check_in_at)} | Checked out {attendanceTime(todayAttendance.check_out_at)} | {todayAttendance.status}</span>;
                    if (todayAttendance.check_in_at) return <span>Checked in {attendanceTime(todayAttendance.check_in_at)} — {todayAttendance.status}{todayAttendance.minutes_late > 0 ? ` (${todayAttendance.minutes_late} min late)` : ""}</span>;
                    return <span>Today: {scheduleLabel} | {currentAttendanceStatus || "Not Checked In"}</span>;
                })()}
                {todayAttendanceAvailability?.attendance_suspended_now && <span>Attendance is excused during this suspension. Essential duty requires Owner/Admin authorization.</span>}
                {attendanceError && <small className="my-attendance-error">{attendanceError}</small>}
            </div>
            {!attendanceLoading && !["On Leave", "Rest Day", "Special Day Off"].includes(todayAttendanceAvailability?.status) && (
                todayAttendance?.check_in_at && !todayAttendance?.check_out_at
                    ? <button type="button" className="workforce-button compact" disabled={Boolean(attendanceAction)} onClick={() => submitAttendanceAction("check-out")}>{attendanceAction === "check-out" ? "Recording…" : "Check Out"}</button>
                    : !todayAttendance?.check_in_at
                        ? <button type="button" className="workforce-button compact" disabled={Boolean(attendanceAction) || todayAttendanceAvailability?.attendance_suspended_now} onClick={() => submitAttendanceAction("check-in")}>{attendanceAction === "check-in" ? "Recording…" : "Check In"}</button>
                        : null
            )}
        </section>

        <FarmEventNotices date={todayKey} timezone={farmTimezone} />
        <nav className="workforce-tabs workforce-primary-tabs my-tasks-primary-tabs" aria-label="My Tasks sections">
            {tabs.map((tab) => <button
                key={tab.id}
                type="button"
                className={`workforce-tab workforce-primary-tab ${activeTab === tab.id ? "active" : ""}`}
                onClick={() => changeTab(tab.id)}
                aria-current={activeTab === tab.id ? "page" : undefined}
            >
                <span className="material-symbols-outlined" aria-hidden="true">{tab.icon}</span>
                <span>{tab.label}</span>
            </button>)}
        </nav>

        {activeTab === "tasks" && <div className="my-tasks-tab-panel" aria-label="Assigned Tasks">
            {error && <div className="workforce-error">{error} <button type="button" className="workforce-button secondary compact" onClick={refreshActiveTab}>Retry</button></div>}
            {groups.held > 0 && <div className="farm-task-held" role="note">{groups.held} tasks held for a farm declaration. Held tasks are excluded from missed counts and need Owner/Admin review.</div>}
            <section className="workforce-stats my-tasks-compact-stats" aria-label="Assignment summary">
                <button type="button" className="workforce-stat total" onClick={() => applySummaryFilter("total")} aria-label={`Show all ${groups.total} active assignments`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">assignment</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">Total Assigned</span><strong>{groups.total}</strong></div>
                </button>
                <button type="button" className="workforce-stat today" onClick={() => applySummaryFilter("today")} aria-label={`Show ${groups.today} tasks due today`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">today</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">Today</span><strong>{groups.today}</strong></div>
                </button>
                <button type="button" className="workforce-stat missed" onClick={() => applySummaryFilter("missed")} aria-label={`Show ${groups.missed} missed or overdue tasks`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">event_busy</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">Missed</span><strong>{groups.missed}</strong></div>
                </button>
                <button type="button" className="workforce-stat progress" onClick={() => applySummaryFilter("progress")} aria-label={`Show ${groups.progress} tasks in progress`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">play_circle</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">In Progress</span><strong>{groups.progress}</strong></div>
                </button>
                <button type="button" className="workforce-stat returned" onClick={() => applySummaryFilter("returned")} aria-label={`Show ${groups.returned} returned tasks`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">assignment_return</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">Returned</span><strong>{groups.returned}</strong></div>
                </button>
                <button type="button" className="workforce-stat review" onClick={() => applySummaryFilter("review")} aria-label={`Show ${groups.review} tasks waiting for review`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">rate_review</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">For Review</span><strong>{groups.review}</strong></div>
                </button>
                <button type="button" className="workforce-stat upcoming" onClick={() => applySummaryFilter("upcoming")} aria-label={`Show ${groups.upcoming} upcoming tasks in the next seven days`}>
                    <div className="workforce-stat-icon"><span className="material-symbols-outlined">event_upcoming</span></div>
                    <div className="workforce-stat-copy"><span className="workforce-stat-label">Upcoming (7 Days)</span><strong>{groups.upcoming}</strong></div>
                </button>
            </section>

            <section className="workforce-card my-assigned-work-card">
                <div className="workforce-card-header my-tasks-toolbar-header">
                    <div>
                        <h2>Assigned Work</h2>
                        <p className="workforce-card-subtitle">Active work is prioritized: returned corrections, missed work, today, in progress, then upcoming assignments.</p>
                    </div>
                    
                </div>
                <div className="my-tasks-filters">
                    <div className="my-tasks-search">
                        <span className="material-symbols-outlined">search</span>
                        <input type="search" placeholder="Search task, resource, field, pen, or location..." value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} aria-label="Search my tasks"/>
                    </div>
                    <select value={taskView} onChange={handleTaskViewChange} aria-label="Filter by task view">
                        {TASK_VIEW_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} aria-label="Filter by priority">
                        <option value="all">All Priorities</option>
                        {priorityOptions.map((priority) => <option key={priority} value={priority}>{priority}</option>)}
                    </select>
                    <select value={scheduleFilter} onChange={(event) => { setScheduleFilter(event.target.value); if (event.target.value !== "date") setSelectedTaskDate(null); }} aria-label="Filter by schedule">
                        <option value="timeline">Active Timeline (Missed, Today & Next 7 Days)</option>
                        <option value="today">Today Only</option>
                        <option value="overdue">Missed / Overdue</option>
                        <option value="upcoming">Upcoming (Next 7 Days)</option>
                        {selectedTaskDate && <option value="date">Selected Date · {formatDateKey(selectedTaskDate, { month: "short", day: "numeric", year: "numeric" })}</option>}
                        <option value="all">All Active Dates</option>
                    </select>
                    <button type="button" className="my-tasks-clear" onClick={clearFilters} disabled={filtersAreDefault}>Clear Filters</button>
                </div>
                {!loading && <div className="my-tasks-results">
                    {taskView === "active" ? <><strong>{groups.total}</strong> active assignment{groups.total === 1 ? "" : "s"}</> : <><strong>{TASK_VIEW_OPTIONS.find(([value]) => value === taskView)?.[1] || "Tasks"}</strong></>}
                    {tasks.length > 0 ? <> · Showing <strong>{filteredTasks.length}</strong> of <strong>{taskTotal}</strong> matching assignments</> : null}
                </div>}
                {loading ? <div className="workforce-empty">Loading your assignments…</div> : error ? (
                    <div className="workforce-empty">
                        <strong>{/not linked|account link problem/i.test(error) ? "Account is not linked to an employee" : "Assignments could not be loaded"}</strong>
                        <span>{error}</span>
                    </div>
                ) : tasks.length === 0 ? <div className="workforce-empty"><strong>No active assignments</strong><span>No tasks are assigned to your employee profile for this view.</span></div> : filteredTasks.length === 0 ? <div className="workforce-empty"><strong>Assignments exist, but the current filters hide them</strong><span>Clear the filters to see your assigned work.</span></div> : <div className="workforce-grid">
                    {filteredTasks.map((task) => {
                        const futureTask = isFutureTaskForView(task, todayKey);
                        const canWorkTask = canWorkTaskForView(task, todayKey);
                        const relatedTo = String(task.related_to || "").trim();
                        const stockShortage = canWorkTask && task.resource_required && task.resource_linked
                            && task.planned_quantity != null && task.planned_inventory_available_quantity != null
                            && Number.isFinite(Number(task.planned_quantity)) && Number.isFinite(Number(task.planned_inventory_available_quantity))
                            && Number(task.planned_inventory_available_quantity) < Number(task.planned_quantity);
                        return <article id={`my-task-${task.id}`} className={`task-card ${String(task.id) === String(focusedTaskId) ? "task-card-deep-link" : ""}`.trim()} tabIndex={String(task.id) === String(focusedTaskId) ? -1 : undefined} key={task.id}>
                        <div className="my-task-card-heading"><div><h3>{task.name}</h3><div className="task-meta"><span>Scheduled {task.activity_date} {task.start_time}</span><span>{task.location}</span><span>{task.priority}</span></div></div><div className="my-task-status-stack"><span className={`task-status ${futureTask ? "upcoming" : statusClass(task.status)}`}>{futureTask ? "Upcoming" : task.status === "Submitted for Review" ? "Awaiting Manager Review" : task.status}</span>{task.is_archived && <span className="task-status archived">Archived</span>}</div></div>
                        {relatedTo && !String(task.name || "").toLowerCase().includes(relatedTo.toLowerCase()) && <p className="my-task-target">{relatedTo}</p>}
                        {task.work_suspended && <div className="farm-task-held"><strong>Held — {task.suspension_holds?.some((x) => x.state === "Review Required") ? "Awaiting reopening review" : "Farm declaration"}</strong><p>{task.suspension_holds?.map((x) => x.title).join("; ")}. Ask the Owner/Admin to review this work or authorize essential duty.</p></div>}
                        {task.assignment_source === "Leave Coverage" && <div className="coverage-task-banner" aria-label={`Leave Coverage — originally assigned to ${task.original_employee_name || "another employee"}`}><span className="material-symbols-outlined">swap_horiz</span><div><strong>Coverage Task — originally assigned to {task.original_employee_name || "another employee"}</strong><span>{task.coverage_start_date} to {task.coverage_end_date}{task.coverage_reason ? ` · ${task.coverage_reason}` : ""}</span></div></div>}
                        {task.assignment_source === "Rest-Day Coverage" && <div className="coverage-task-banner"><span className="material-symbols-outlined">event_available</span><div><strong>Rest-Day Coverage</strong><span>This task is temporarily assigned to you while the default employee is on a scheduled rest day.</span></div></div>}
                        {task.needs_reassignment && <div className="task-missed-banner"><span className="material-symbols-outlined">warning</span><div><strong>Availability Warning / Needs Coverage</strong><span>The manager kept this assignment despite an availability conflict. The task remains visible to you.</span></div></div>}
                        {isMissedTask(task, todayKey) && <div className="task-missed-banner"><span className="material-symbols-outlined">warning</span><div><strong>Missed / Overdue</strong><span>Due {task.activity_date} · {daysOverdue(task, todayKey)} day{daysOverdue(task, todayKey) === 1 ? "" : "s"} overdue. Complete it now or report the problem.</span></div></div>}
                        {futureTask && !READ_ONLY_TASK_STATUSES.has(task.status) && !task.is_archived && <div className="task-upcoming-lock-note" role="note"><span className="material-symbols-outlined" aria-hidden="true">lock_clock</span><div><strong>Upcoming Task</strong><span>This task is scheduled for {formatDateKey(task.activity_date, { month: "short", day: "numeric", year: "numeric" })}. Start and Submit Work will appear on that day.</span></div></div>}
                        {task.resource_required && task.resource_linked && <div className="task-note my-task-resource-summary"><strong>Inventory resource:</strong> {task.planned_inventory_item_name || "Linked item"}{task.planned_quantity != null ? <> · Planned <strong>{task.planned_quantity} {task.planned_inventory_unit || task.planned_unit || ""}</strong></> : null}</div>}
                        {stockShortage && <div className="task-missed-banner" role="note" aria-label="Stock check needed"><span className="material-symbols-outlined" aria-hidden="true">inventory_2</span><div><strong>Stock check needed</strong><span>{task.planned_inventory_available_quantity} {task.planned_inventory_unit || task.planned_unit || ""} available against {task.planned_quantity} {task.planned_inventory_unit || task.planned_unit || ""} planned. Check with your manager before using this resource.</span></div></div>}
                        {task.resource_required && !task.resource_linked && !READ_ONLY_TASK_STATUSES.has(task.status) && !task.is_archived && <div className="workforce-error" style={{marginTop:10,marginBottom:0}}><strong>Inventory resource not linked.</strong> Ask the manager to link the appropriate feed, vaccine, fertilizer, medicine, or other allowed resource before submitting this task.</div>}
                        {!task.resource_required && task.planned_quantity != null && <div className="task-note">Planned quantity: <strong>{task.planned_quantity} {task.planned_unit || ""}</strong></div>}
                        {task.status === "Returned" && task.latest_submission?.review_feedback && <div className="workforce-error my-task-correction-note"><strong>Manager feedback:</strong> {task.latest_submission.review_feedback}</div>}
                        {task.status === "Completed" ? <div className="task-readonly-note">Completed work is read-only.</div> : (READ_ONLY_TASK_STATUSES.has(task.status) || task.is_archived) && <div className="task-readonly-note">Historical work is read-only.</div>}
                        <details className="my-task-details" open={expandedTaskIds.has(String(task.id))} onToggle={(event) => {
                            const open = event.currentTarget.open;
                            setExpandedTaskIds((current) => {
                                const id = String(task.id);
                                if (current.has(id) === open) return current;
                                const next = new Set(current);
                                if (open) next.add(id); else next.delete(id);
                                return next;
                            });
                        }}>
                            <summary aria-label={`Details for ${task.name}`}>
                                <span className="my-task-details-show">View details</span>
                                <span className="my-task-details-hide">Hide details</span>
                            </summary>
                            <div className="my-task-details-content">
                                {task.instructions && <div className="task-note"><strong>Instructions:</strong> {task.instructions}</div>}
                                {task.description && <p className="workforce-card-subtitle">{task.description}</p>}
                                {!task.instructions && !task.description && <p className="workforce-card-subtitle">No additional instructions provided.</p>}
                                {task.resource_required && task.resource_linked && task.planned_inventory_available_quantity != null && <div className="task-note"><strong>Available stock:</strong> {task.planned_inventory_available_quantity} {task.planned_inventory_unit || task.planned_unit || ""}</div>}
                                {task.status === "Completed" && task.latest_submission?.submitted_at && String(task.latest_submission.submitted_at).slice(0,10) > task.activity_date && <div className="task-late-completion"><span className="material-symbols-outlined" aria-hidden="true">schedule</span>Completed late · submitted {String(task.latest_submission.submitted_at).slice(0,10)}</div>}
                                {task.status === "Completed" ? <>
                                    <div className="task-note"><strong>Completion date:</strong> {task.completed_at ? new Date(task.completed_at).toLocaleString() : "Not recorded"}</div>
                                    <div className="task-note"><strong>Actual quantity:</strong> {task.latest_submission?.actual_quantity != null ? `${task.latest_submission.actual_quantity} ${task.latest_submission.actual_unit || ""}`.trim() : "Not recorded"}</div>
                                    <ObservationSummary observation={task.latest_submission?.monitoring} />
                                    <div className="task-note"><strong>Employee notes:</strong> {task.latest_submission?.worker_notes || "No notes provided."}</div>
                                    <div className="task-note"><strong>Manager feedback:</strong> {task.latest_submission?.review_feedback || "No feedback provided."}</div>
                                </> : <>
                                    {task.status !== "Returned" && task.latest_submission?.review_feedback && <div className="task-note"><strong>Manager feedback:</strong> {task.latest_submission.review_feedback}</div>}
                                    {task.latest_submission?.actual_quantity != null && <div className="task-note">Last actual usage: <strong>{task.latest_submission.actual_quantity} {task.latest_submission.actual_unit || ""}</strong></div>}
                                    {task.latest_submission?.worker_notes && <div className="task-note"><strong>Employee notes:</strong> {task.latest_submission.worker_notes}</div>}
                                    {task.latest_submission?.submitted_at && task.status === "Submitted for Review" && <div className="task-note"><strong>Submitted:</strong> {new Date(task.latest_submission.submitted_at).toLocaleString()}</div>}
                                    {task.status === "Submitted for Review" && <div className="task-note"><strong>Awaiting Manager Review:</strong> Your submitted work is waiting for a manager or reviewer. You cannot submit another attempt unless it is returned for correction.{task.resource_required ? " The reported inventory quantity is reserved; stock will be deducted only if the work is approved." : ""}</div>}
                                </>}
                                {task.latest_submission?.evidence_url && <div className="task-note my-task-evidence-history"><strong>Evidence:</strong> <EvidenceViewButton evidenceUrl={task.latest_submission.evidence_url} compact/></div>}
                            </div>
                        </details>
                        {(canWorkTask || task.latest_submission || task.problem_report) && <div className="task-actions">
                            {!futureTask && canWorkTask && ["Pending","Returned"].includes(task.status) && <button className="workforce-button secondary" onClick={() => startTask(task)}>Start</button>}
                            {!futureTask && canWorkTask && ["Pending","In Progress","Returned"].includes(task.status) && <button className="workforce-button" disabled={task.resource_required && !task.resource_linked} onClick={() => openSubmit(task)}>{task.resource_required && !task.resource_linked ? "Resource Link Needed" : task.status === "Returned" ? "Correct & Submit" : "Submit Work"}</button>}
                            {task.can_void && task.status === "Completed" && task.latest_submission?.review_status === "Approved" && <button type="button" className="workforce-button secondary" onClick={async () => {
                                if (await requestVoid({ action: "task", recordId: task.id })) {
                                    notification.success("Owner/Admin authorized the void. The original history is retained.", "Work Voided");
                                    await loadTasks(backendTaskView, { force: true, sharedDevice: sharedDeviceMode, scope: backendTaskScope });
                                    await loadTaskSummary();
                                }
                            }}>Request Void</button>}
                            {(task.latest_submission || task.problem_report) && <button type="button" className="workforce-button secondary" onClick={() => setReportId(task.id)}>View Report</button>}
                        </div>}
                    </article>;
                    })}
                </div>}
                {!loading && tasks.length < taskTotal && <div className="assignment-load-more">
                    <button type="button" className="workforce-button secondary" disabled={loadingMore} onClick={loadMoreTasks}>
                        {loadingMore ? "Loading…" : "Load 25 More"}
                    </button>
                    <span>{taskTotal - tasks.length} more assignments</span>
                </div>}
            </section>
        </div>}

        {activeTab === "schedule" && <section className="workforce-card my-schedule-card my-tasks-tab-panel" aria-label="My Schedule">
            <div className="workforce-card-header my-tasks-toolbar-header">
                <div><h2>My Schedule</h2><p className="workforce-card-subtitle">Your roster, attendance, approved leave, and active assignments for the week · {farmTimezone}.</p></div>
                <div className="my-schedule-actions">
                    <button type="button" className="workforce-button secondary" onClick={() => setScheduleWeekStart((current) => addCalendarDays(current, -7))}>Previous</button>
                    <button type="button" className="workforce-button secondary" onClick={() => setScheduleWeekStart(startOfWeekKey(farmToday))}>This Week</button>
                    <button type="button" className="workforce-button secondary" onClick={() => setScheduleWeekStart((current) => addCalendarDays(current, 7))}>Next</button>
                    
                </div>
            </div>
            {scheduleError && <div className="workforce-error">{scheduleError} <button type="button" className="workforce-button secondary compact" onClick={refreshMySchedule}>Retry</button></div>}
            {scheduleLoading && scheduleLoadedRange !== scheduleRangeKey ? <div className="workforce-empty">Loading your weekly schedule…</div> : <div className="my-schedule-week">
                {dateKeysBetween(scheduleWeekStart, scheduleWeekEnd).map((key) => {
                    const shiftRows = (scheduleData.shifts || []).filter((item) => item.work_date === key && item.status !== "Cancelled");
                    const attendanceRows = (scheduleData.attendance || []).filter((item) => item.attendance_date === key);
                    const leaveRows = (scheduleData.leave || []).filter((item) => item.start_date <= key && item.end_date >= key && item.status === "Approved");
                    const taskCount = (scheduleData.tasks || []).filter((item) => item.activity_date === key && !CLOSED_TASK_STATUSES.has(item.status)).length;
                    const availability = (scheduleData.availability || []).find((item) => item.work_date === key) || null;
                    const shiftStart = availability?.start_time ? String(availability.start_time).slice(0, 5) : null;
                    const shiftEnd = availability?.end_time ? String(availability.end_time).slice(0, 5) : null;
                    return <article key={key} className={`my-schedule-day ${key === farmToday ? "today" : ""}`}>
                        <strong>{formatDateKey(key, { weekday: "short", month: "short", day: "numeric" })}</strong>
                        {availability && <span className={`my-schedule-state ${String(availability.status || "").toLowerCase().replaceAll(" ", "-")}`}>{availability.status}: {availability.reason}</span>}
                        {availability?.schedule_status === "Needs Setup" && <span className="my-schedule-needs-setup">Schedule setup required — legacy availability is being preserved.</span>}
                        {availability?.exception_type && <span>Schedule exception: {availability.exception_type}</span>}
                        {shiftStart ? <span>Scheduled shift: {shiftStart}{shiftEnd ? `–${shiftEnd}` : ""}</span> : shiftRows.length ? shiftRows.map((item) => <span key={`shift-${item.id}`}>Roster: {item.start_time ? String(item.start_time).slice(0, 5) : "All day"}{item.end_time ? `–${String(item.end_time).slice(0, 5)}` : ""}{item.assigned_area ? ` · ${item.assigned_area}` : ""}</span>) : <span>{availability?.status === "Rest Day" || availability?.status === "Special Day Off" ? "No shift — scheduled day off" : "No roster shift"}</span>}
                        {key <= farmToday ? (attendanceRows.length ? attendanceRows.map((item) => <span key={`att-${item.id}`}>Attendance: {attendanceStatusForSchedule(item, availability)}</span>) : <span>Attendance: Not recorded</span>) : <span>Attendance: Future date</span>}
                        {leaveRows.map((item) => <span key={`leave-${item.id}`} className="my-schedule-leave-row">Approved leave: {item.leave_type}</span>)}
                        <span>{taskCount} active assignment{taskCount === 1 ? "" : "s"}</span>
                        {taskCount > 0 && <button type="button" className="my-schedule-task-link" onClick={() => openTasksForDate(key)}>Open Assigned Tasks for this day</button>}
                    </article>;
                })}
            </div>}
        </section>}

        {activeTab === "leave" && <div className="my-leave-tab-stack my-tasks-tab-panel" aria-label="Leave Requests">
            <form className="my-leave-request workforce-card" onSubmit={submitLeaveRequest}>
                <div className="my-leave-request-heading my-tasks-toolbar-header">
                    <div><h2>Request Leave</h2><p>Choose dates from tomorrow onward. Requests are submitted as Pending for manager or administrator approval.</p></div>
                    
                </div>
                <div className="my-leave-request-grid">
                    <label className="workforce-field"><span>Leave type</span><select value={leaveRequest.leave_type} onChange={(event) => setLeaveRequest((current) => ({ ...current, leave_type: event.target.value }))} disabled={leaveSubmitting}><option>Sick Leave</option><option>Vacation Leave</option><option>Emergency Leave</option><option>Day Off</option><option>Other</option></select></label>
                    <label className="workforce-field"><span>Start date</span><input type="date" required min={minimumLeaveDate} value={leaveRequest.start_date} onChange={(event) => setLeaveRequest((current) => ({ ...current, start_date: event.target.value, end_date: current.end_date < event.target.value ? event.target.value : current.end_date }))} disabled={leaveSubmitting}/></label>
                    <label className="workforce-field"><span>End date</span><input type="date" required min={leaveRequest.start_date > minimumLeaveDate ? leaveRequest.start_date : minimumLeaveDate} value={leaveRequest.end_date} onChange={(event) => setLeaveRequest((current) => ({ ...current, end_date: event.target.value }))} disabled={leaveSubmitting}/></label>
                    <label className="workforce-field my-leave-reason"><span>Reason <small>{leaveReasonRequired ? "(required)" : "(optional)"}</small></span><input type="text" required={leaveReasonRequired} value={leaveRequest.reason} maxLength={1000} placeholder="Reason for leave" onChange={(event) => setLeaveRequest((current) => ({ ...current, reason: event.target.value }))} disabled={leaveSubmitting}/></label>
                </div>
                <div className="my-leave-request-actions"><button type="submit" className="workforce-button" disabled={leaveSubmitting}>{leaveSubmitting ? "Submitting…" : "Submit Leave Request"}</button></div>
            </form>

            <section className="my-leave-history workforce-card" aria-label="My Leave Requests">
                <div className="my-leave-history-heading"><h2>My Leave Requests</h2><p>Track approval status, reviewer feedback, and coverage. Only Pending requests can be cancelled by employees.</p></div>
                {leaveError && <div className="workforce-error">{leaveError} <button type="button" className="workforce-button secondary compact" onClick={refreshMyLeaveRequests}>Retry</button></div>}
                {leaveLoading && !leaveLoaded ? <p className="workforce-empty compact">Loading leave requests…</p> : myLeaveRequests.length === 0 ? <p className="workforce-empty compact">No leave requests yet.</p> : <div className="my-leave-history-list">
                    {myLeaveRequests.map((item) => <article className="my-leave-history-row" key={item.id}>
                        <div><strong>{item.leave_type}</strong><span>{item.start_date}{item.end_date !== item.start_date ? ` to ${item.end_date}` : ""}</span>{item.reason && <span>Reason: {item.reason}</span>}</div>
                        <span className={`leave-status-badge ${statusClass(item.status)}`}>{item.status}</span>
                        <div className="my-leave-history-feedback">
                            <span>Submitted: {item.request_date ? new Date(item.request_date).toLocaleString() : "—"}</span>
                            <span>Reviewer: {item.reviewed_by_name || "Not reviewed yet"}</span>
                            {item.decided_at && <span>Reviewed: {new Date(item.decided_at).toLocaleString()}</span>}
                            {item.decision_notes && <span>Manager feedback: {item.decision_notes}</span>}
                            {item.default_covering_employee_name && <span>Default coverage: {item.default_covering_employee_name}</span>}
                            {item.affected_task_count > 0 && <span>Coverage impact: {item.affected_task_count} task{item.affected_task_count === 1 ? "" : "s"}</span>}
                            {item.coverage_reason && <span>Coverage information: {item.coverage_reason}</span>}
                            {item.cancelled_by_name && <span>Cancelled by {item.cancelled_by_name}{item.cancelled_at ? ` · ${new Date(item.cancelled_at).toLocaleString()}` : ""}</span>}
                            {item.cancellation_reason && <span>Cancellation: {item.cancellation_reason}</span>}
                        </div>
                        {item.status === "Pending" && <button type="button" className="my-schedule-leave-cancel" onClick={() => cancelOwnLeave(item.id)}>Cancel Pending Request</button>}
                    </article>)}
                </div>}
            </section>
        </div>}
    </main>

    {reportTask && <div className="my-task-submit-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setReportId(null); }}>
        <div className="my-task-submit-modal my-task-report-modal" role="dialog" aria-modal="true" aria-labelledby="my-task-report-title" onMouseDown={(event) => event.stopPropagation()}>
            <header className="my-task-submit-header"><div><h2 id="my-task-report-title">Work Report</h2><p>Read-only submission details for <strong>{reportTask.name}</strong>.</p></div><button type="button" className="my-task-submit-close" onClick={() => setReportId(null)} aria-label="Close work report"><span className="material-symbols-outlined">close</span></button></header>
            <div className="my-task-report-body">
                <div className="my-task-submit-detail-grid"><div><span>Status</span><strong>{reportTask.status}</strong></div><div><span>Scheduled</span><strong>{reportTask.activity_date}</strong></div><div><span>Location</span><strong>{reportTask.location || "Not specified"}</strong></div><div><span>Priority</span><strong>{reportTask.priority || "Normal"}</strong></div></div>
                {reportTask.latest_submission ? <div className="my-task-report-details">
                    <div className="task-note"><strong>Submitted:</strong> {reportTask.latest_submission.submitted_at ? new Date(reportTask.latest_submission.submitted_at).toLocaleString() : "Not recorded"}</div>
                    <div className="task-note"><strong>Actual quantity:</strong> {reportTask.latest_submission.actual_quantity != null ? `${reportTask.latest_submission.actual_quantity} ${reportTask.latest_submission.actual_unit || ""}`.trim() : "Not recorded"}</div>
                    <div className="task-note"><strong>Employee notes:</strong> {reportTask.latest_submission.worker_notes || "No notes provided."}</div>
                    <div className="task-note"><strong>Problem report:</strong> {reportTask.latest_submission.problem_report || reportTask.problem_report || "No problem reported."}</div>
                    <div className="task-note"><strong>Manager feedback:</strong> {reportTask.latest_submission.review_feedback || "No feedback provided."}</div>
                    {reportTask.latest_submission.evidence_url && <div className="task-note my-task-evidence-history"><strong>Evidence:</strong> <EvidenceViewButton evidenceUrl={reportTask.latest_submission.evidence_url} compact/></div>}
                </div> : <div className="workforce-empty compact">No submitted work report is recorded for this task yet.</div>}
            </div>
        </div>
    </div>}
    {submitTask && <div
        className="my-task-submit-overlay"
        onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSubmitId(null);
        }}
    >
        <div
            className="my-task-submit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="my-task-submit-title"
            onMouseDown={(event) => event.stopPropagation()}
        >
            <header className="my-task-submit-header">
                <div>
                    <h2 id="my-task-submit-title">Submit Work</h2>
                    <p>Record the actual work completed for <strong>{submitTask.name}</strong>.</p>
                </div>
                <button type="button" className="my-task-submit-close" onClick={()=>setSubmitId(null)} aria-label="Close submit work modal">
                    <span className="material-symbols-outlined">close</span>
                </button>
            </header>

            <form className="my-task-submit-form" onSubmit={(event)=>submit(event, submitTask)}>
                <section className="my-task-submit-section my-task-submit-summary">
                    <div className="my-task-submit-section-title">
                        <span className="material-symbols-outlined">assignment</span>
                        <div>
                            <h3>Task Details</h3>
                            <p>Confirm the assignment before submitting your work.</p>
                        </div>
                    </div>
                    <div className="my-task-submit-detail-grid">
                        <div><span>Task</span><strong>{submitTask.name}</strong></div>
                        <div><span>Due Date</span><strong>{submitTask.activity_date || "—"}</strong></div>
                        <div><span>Location</span><strong>{submitTask.location || "Not specified"}</strong></div>
                        <div><span>Priority</span><strong>{submitTask.priority || "Normal"}</strong></div>
                        {submitTask.assignment_source === "Leave Coverage" && <>
                            <div><span>Original employee</span><strong>{submitTask.original_employee_name || "—"}</strong></div>
                            <div><span>Covering employee</span><strong>{submitTask.covering_employee_name || submitTask.employee_name || "—"}</strong></div>
                            <div><span>Related leave</span><strong>{submitTask.coverage_start_date} to {submitTask.coverage_end_date}</strong></div>
                            <div><span>Coverage reason</span><strong>{submitTask.coverage_reason || "Approved leave coverage"}</strong></div>
                        </>}
                    </div>
                    {isMissedTask(submitTask, todayKey) && <div className="task-missed-banner">
                        <span className="material-symbols-outlined">warning</span>
                        <div><strong>Missed / Overdue</strong><span>Due {submitTask.activity_date} · {daysOverdue(submitTask, todayKey)} day{daysOverdue(submitTask, todayKey) === 1 ? "" : "s"} overdue.</span></div>
                    </div>}
                    {submitTask.resource_required && submitTask.resource_linked && <div className="my-task-submit-resource">
                        <span className="material-symbols-outlined">inventory_2</span>
                        <div>
                            <span>Inventory Resource</span>
                            <strong>{submitTask.planned_inventory_item_name || "Linked item"}</strong>
                            <small>Planned: {submitTask.planned_quantity ?? "—"} {submitTask.planned_inventory_unit || submitTask.planned_unit || ""}{submitTask.planned_inventory_available_quantity != null ? ` · Available: ${submitTask.planned_inventory_available_quantity} ${submitTask.planned_inventory_unit || ""}` : ""}</small>
                        </div>
                    </div>}
                </section>

                <section className="my-task-submit-section">
                    <div className="my-task-submit-section-title">
                        <span className="material-symbols-outlined">fact_check</span>
                        <div>
                            <h3>Work Submission</h3>
                            <p>Enter what was actually completed. The actual inventory quantity is reserved now and deducted only after manager approval.</p>
                        </div>
                    </div>
                    <div className="my-task-submit-form-grid">
                        {isCropHarvestSubmission && <div className="workforce-field full">
                            <label htmlFor="my-task-harvest-type">Harvest Type *</label>
                            <select id="my-task-harvest-type" required value={form.harvest_type_intent} onChange={(event)=>setForm({...form,harvest_type_intent:event.target.value})}>
                                <option value="">Select harvest type</option>
                                <option value="Partial Harvest">Partial Harvest</option>
                                <option value="Final Harvest">Final/Fully Harvested</option>
                            </select>
                            <small>This is the harvest type you are reporting. The crop will stay unchanged until the manager confirms it in Task Management.</small>
                        </div>}
                        {(submitTask.resource_required || isCropHarvestSubmission) && <>
                            <div className="workforce-field">
                                <label htmlFor="my-task-actual-quantity">{isCropHarvestSubmission ? "Actual Harvest Yield *" : "Actual Quantity Used *"}</label>
                                <input id="my-task-actual-quantity" type="number" min="0.001" step="0.001" required autoFocus value={form.actual_quantity} onChange={(event)=>setForm({...form,actual_quantity:event.target.value})}/>
                                <small>{isCropHarvestSubmission ? "Enter only the quantity harvested in this occurrence. Your reported Partial/Final type waits for manager confirmation before Crops changes." : "The actual quantity is reserved when you submit. Inventory is deducted only after Admin/Manager approval."}</small>
                            </div>
                            <div className="workforce-field">
                                <label htmlFor="my-task-actual-unit">{isCropHarvestSubmission ? "Harvest Unit" : "Inventory Unit"}</label>
                                <input id="my-task-actual-unit" value={form.actual_unit || (isCropHarvestSubmission ? "kg" : "")} readOnly/>
                            </div>
                        </>}
                        <MonitoringObservationFields context={submitTask.monitoring_context} value={form.monitoring} onChange={(monitoring) => setForm({ ...form, monitoring })} disabled={submitting} />
                        <EvidencePhotoField
                            taskId={submitTask.id}
                            value={form.evidence_url}
                            onChange={(value)=>setForm({...form,evidence_url:value})}
                            required={submitTask.requires_evidence}
                            label="Evidence Photo"
                            helpText="Take or upload a photo of the completed work."
                        />
                        <div className="workforce-field full">
                            <label htmlFor="my-task-work-notes">Work Notes</label>
                            <textarea id="my-task-work-notes" placeholder="What was done?" value={form.worker_notes} onChange={(event)=>setForm({...form,worker_notes:event.target.value})}/>
                        </div>
                        <div className="workforce-field full">
                            <label htmlFor="my-task-problem-report">Report a Problem <span className="field-optional">Optional</span></label>
                            <textarea id="my-task-problem-report" placeholder="Equipment issue, animal problem, shortage, delay…" value={form.problem_report} onChange={(event)=>setForm({...form,problem_report:event.target.value})}/>
                        </div>
                    </div>
                </section>

                <footer className="my-task-submit-footer">
                    <button className="my-task-submit-cancel" type="button" onClick={()=>setSubmitId(null)} disabled={submitting}>
                        <span className="material-symbols-outlined">close</span>
                        Cancel
                    </button>
                    <button className="my-task-submit-save" type="submit" disabled={submitting}>
                        <span className="material-symbols-outlined">send</span>
                        {submitting ? "Submitting…" : "Submit for Review"}
                    </button>
                </footer>
            </form>
        </div>
    </div>}
    </div>;
}

export default MyTasks;
