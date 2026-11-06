"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FarmEventPanel, CalendarEventBands } from "../../components/FarmEvents/FarmEvents.jsx";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { workforceService } from "../../services/workforceService.js";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import { useAuth } from "../../context/AuthContext.jsx";
import {
    DEFAULT_FARM_TIMEZONE,
    dateKeysBetween,
    farmDateKey,
    moveCalendarAnchor,
} from "../../utils/farmCalendar.js";
import {
    buildCalendarReturnPath,
    calendarDisplayRange,
    employeeMatchesAvailabilityFilter,
    isActiveCalendarTask,
    isScheduledCalendarRow,
    isTemporarilyCoveredTask,
    normalizeAvailabilityFilter,
    normalizeCalendarView,
    taskNeedsCoverage,
} from "./staffCalendarView.js";
import StaffCalendarViews from "./StaffCalendarViews.jsx";
import StaffAttendanceSummary from "./StaffAttendanceSummary.jsx";
import { indexStaffCalendar, matchesAttendanceFilter, staffDayRow, summarizeStaffAttendance, validateStaffCalendarPayload } from "./staffAttendance.js";
import StaffCalendarDetailsModal from "./StaffCalendarDetailsModal.jsx";
import { StaffCalendarHeading, StaffCalendarToolbar } from "./StaffCalendarToolbar.jsx";
import "./StaffCalendar.css";

const emptyCalendar = () => ({ tasks: [], attendance: [], leave: [], shifts: [], availability: [] });

function StaffCalendar() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { hasPermission } = useAuth();
    const canManage = hasPermission("workforce:manage") || hasPermission("workforce:attendance");
    const canManageSchedule = hasPermission("workforce:manage");

    const [eventPanel, setEventPanel] = useState(() => searchParams.get("eventAction") === "create" ? { initial: {
        kind: searchParams.get("kind"), title: searchParams.get("title") || "", reason: searchParams.get("reason") || "",
        source_name: searchParams.get("source") || "", source_reference: searchParams.get("reference") || "",
    } } : searchParams.get("eventId") ? { id: Number(searchParams.get("eventId")) } : null);
    const [farmTimezone, setFarmTimezone] = useState(DEFAULT_FARM_TIMEZONE);
    const [todayKey, setTodayKey] = useState(() => farmDateKey(new Date(), DEFAULT_FARM_TIMEZONE));
    const [mode, setMode] = useState(() => searchParams.get("selectedDate") ? "day" : normalizeCalendarView(searchParams.get("view")));
    const [anchor, setAnchor] = useState(() => searchParams.get("selectedDate") || searchParams.get("date") || farmDateKey(new Date(), DEFAULT_FARM_TIMEZONE));
    const [employeeId, setEmployeeId] = useState(() => searchParams.get("employeeId") || "");
    const [availabilityFilter, setAvailabilityFilter] = useState(() => normalizeAvailabilityFilter(searchParams.get("availability")));
    // selectedDate is an editor target. Older selectedDate links resolve to Day view above.
    const [selectedDate, setSelectedDate] = useState("");
    const [employees, setEmployees] = useState([]);
    const [employeesReady, setEmployeesReady] = useState(false);
    const [employeesError, setEmployeesError] = useState("");
    const [configReady, setConfigReady] = useState(false);
    const [configError, setConfigError] = useState("");
    const [todayData, setTodayData] = useState(null);
    const [todayError, setTodayError] = useState("");
    const [loadedRange, setLoadedRange] = useState("");
    const [updatedAt, setUpdatedAt] = useState(null);
    const [actionMessage, setActionMessage] = useState("");
    const [actionError, setActionError] = useState("");
    const actionBusyRef = useRef(false);
    const [data, setData] = useState(emptyCalendar);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [editor, setEditor] = useState(null);
    const [attendanceForm, setAttendanceForm] = useState({ employee_id: "", attendance_date: "", status: "Present", notes: "", correction_reason: "" });
    const [attendanceBusy, setAttendanceBusy] = useState("");
    const [shiftForm, setShiftForm] = useState({
        id: null,
        employee_id: "",
        work_date: "",
        start_time: "",
        end_time: "",
        assigned_area: "",
        status: "Scheduled",
        notes: "",
        exception_type: "",
        exception_reason: "",
    });
    const requestSequenceRef = useRef(0);
    const detailsModalRef = useRef(null);
    const calendarSectionRef = useRef(null);
    const previousFocusRef = useRef(null);
    const [portalReady, setPortalReady] = useState(false);
    const initialDateProvidedRef = useRef(Boolean(searchParams.get("date") || searchParams.get("selectedDate")));

    const range = useMemo(() => calendarDisplayRange(anchor, mode), [anchor, mode]);
    const days = useMemo(() => dateKeysBetween(range[0], range[1]), [range]);
    const activeEmployees = useMemo(() => employees.filter((employee) => !employee.is_archived && employee.employment_status !== "Inactive"), [employees]);
    const employeeNames = useMemo(() => new Map(employees.map((item) => [Number(item.id), item.full_name])), [employees]);

    useEffect(() => {
        setPortalReady(true);
    }, []);

    const loadConfig = useCallback(async () => {
        try {
            const config = await workforceService.getCalendarConfig();
            const nextTimezone = config.timezone || DEFAULT_FARM_TIMEZONE;
            const nextToday = config.today || farmDateKey(new Date(), nextTimezone);
            setFarmTimezone(nextTimezone);
            setTodayKey(nextToday);
            setConfigError("");
            if (!initialDateProvidedRef.current) {
                setAnchor(nextToday);
                initialDateProvidedRef.current = true;
            }
            setConfigReady(true);
        } catch (err) {
            setConfigError(err?.message || "Unable to confirm the farm date.");
        }
    }, []);
    const loadEmployees = useCallback(async () => {
        if (!canManage) return;
        try {
            const rows = await workforceService.getEmployees();
            setEmployees(rows || []);
            setEmployeesReady(true);
            setEmployeesError("");
        } catch (err) {
            setEmployeesError(err?.message || "Unable to load employees.");
        }
    }, [canManage]);
    useEffect(() => { loadConfig(); }, [loadConfig]);
    useEffect(() => { loadEmployees(); }, [loadEmployees]);
    const rangeKey = range.join(":");
    const loadCalendar = useCallback(async ({ background = false } = {}) => {
        if (!configReady || !canManage) return;
        const requestId = ++requestSequenceRef.current;
        if (background) setRefreshing(true);
        else setLoading(true);
        const todayInRange = range[0] <= todayKey && range[1] >= todayKey;
        // One bounded request for the calendar, plus today only when outside that range.
        const ranges = [range, ...(!todayInRange ? [[todayKey, todayKey]] : [])];
        const results = await Promise.allSettled(ranges.map(([from, to]) => workforceService.getCalendar(from, to, null).then(validateStaffCalendarPayload)));
        if (requestId !== requestSequenceRef.current) return;
        if (results[0].status === "fulfilled") {
            setData(results[0].value);
            setLoadedRange(rangeKey);
            setUpdatedAt(new Date().toISOString());
            setError("");
        } else setError(results[0].reason?.message || "Unable to load staff calendar.");
        const todayResult = results[todayInRange ? 0 : 1];
        if (todayResult.status === "fulfilled") {
            setTodayData({ date: todayKey, data: todayResult.value, updatedAt: new Date().toISOString() });
            setTodayError("");
        } else setTodayError(todayResult.reason?.message || "Unable to load today’s attendance.");
        setLoading(false);
        setRefreshing(false);
    }, [range, rangeKey, todayKey, configReady, canManage]);
    useEffect(() => {
        loadCalendar();
        return () => { requestSequenceRef.current += 1; };
    }, [loadCalendar]);
    const refreshCalendar = useCallback(async () => {
        if (actionBusyRef.current) return;
        await Promise.all([loadConfig(), loadEmployees(), loadCalendar({ background: true })]);
    }, [loadConfig, loadEmployees, loadCalendar]);
    useFarmModuleUpdates(["calendar", "tasks", "employees"], refreshCalendar, { editing: Boolean(editor || eventPanel) });
    useEffect(() => {
        const timer = window.setInterval(() => {
            if (!editor && !eventPanel && document.visibilityState === "visible") refreshCalendar();
        }, 60000);
        return () => window.clearInterval(timer);
    }, [editor, eventPanel, refreshCalendar]);

    useEffect(() => {
        const nextPath = buildCalendarReturnPath({
            view: mode,
            anchor,
            employeeId,
            availability: availabilityFilter,
        });
        const current = `${window.location.pathname}${window.location.search}`;
        if (current !== nextPath) window.history.replaceState(window.history.state, "", nextPath);
    }, [mode, anchor, employeeId, availabilityFilter]);

    const dataIndex = useMemo(() => indexStaffCalendar(data), [data]);
    const todayIndex = useMemo(() => indexStaffCalendar(todayData?.data), [todayData]);
    const tasksByDate = dataIndex.tasks;
    const selectedEmployees = useMemo(() => employeeId
        ? activeEmployees.filter((employee) => String(employee.id) === String(employeeId))
        : activeEmployees, [activeEmployees, employeeId]);
    const employeeDayRow = useCallback((employee, dateKey) => staffDayRow(dataIndex, employee, dateKey, todayKey), [dataIndex, todayKey]);
    const todayRows = useMemo(() => selectedEmployees.map((employee) => staffDayRow(todayIndex, employee, todayKey, todayKey)), [selectedEmployees, todayIndex, todayKey]);
    const todaySummary = useMemo(() => summarizeStaffAttendance(todayRows,
        (todayIndex.tasks.get(todayKey) || []).filter((task) => !employeeId || [task.assigned_employee_id, task.original_employee_id, task.covering_employee_id].some((id) => String(id) === String(employeeId))), todayKey), [todayRows, todayIndex, todayKey, employeeId]);
    const todayReady = employeesReady && !employeesError && configReady && !configError && todayData?.date === todayKey && !todayError;
    const editorIndex = editor?.dateKey === todayKey && todayData?.date === todayKey ? todayIndex : dataIndex;

    const rowsForDate = useCallback((dateKey) => selectedEmployees
        .map((employee) => employeeDayRow(employee, dateKey))
        .filter((row) => employeeMatchesAvailabilityFilter({ filter: availabilityFilter, state: row.state, tasks: row.tasks }) && matchesAttendanceFilter(row, availabilityFilter, todayKey)),
    [selectedEmployees, employeeDayRow, availabilityFilter, todayKey]);

    const summaryForDate = useCallback((dateKey) => {
        const rows = rowsForDate(dateKey);
        const selectedIds = new Set(selectedEmployees.map((employee) => Number(employee.id)));
        const dateTasks = (tasksByDate.get(dateKey) || []).filter((task) => (
            !employeeId
            || selectedIds.has(Number(task.assigned_employee_id))
            || selectedIds.has(Number(task.original_employee_id))
            || selectedIds.has(Number(task.covering_employee_id))
        ));
        const dateLeaves = (data.leave || []).filter((leave) => (
            selectedIds.has(Number(leave.employee_id))
            && leave.start_date <= dateKey
            && leave.end_date >= dateKey
        ));
        return {
            rows,
            scheduled: rows.filter(isScheduledCalendarRow).length,
            present: rows.filter((row) => row.state === "Present").length,
            possibleAbsence: rows.filter((row) => row.state === "Possible Absence").length,
            absent: rows.filter((row) => row.state === "Absent").length,
            late: rows.filter((row) => row.state === "Late").length,
            sick: rows.filter((row) => row.state === "Sick").length,
            leave: rows.filter((row) => ["Approved Leave", "On Leave"].includes(row.state)).length,
            rest: rows.filter((row) => row.state === "Rest Day").length,
            needsCoverage: dateTasks.filter(taskNeedsCoverage).length,
            covered: dateTasks.filter(isTemporarilyCoveredTask).length,
            activeTasks: dateTasks.filter(isActiveCalendarTask),
            pendingLeaves: dateLeaves.filter((leave) => leave.status === "Pending"),
            approvedLeaves: dateLeaves.filter((leave) => leave.status === "Approved"),
        };
    }, [rowsForDate, selectedEmployees, employeeId, tasksByDate, data.leave]);

    const summariesByDate = useMemo(() => new Map(
        days.map((dateKey) => [dateKey, summaryForDate(dateKey)]),
    ), [days, summaryForDate]);
    const summaryForDisplay = useCallback((dateKey) => (
        summariesByDate.get(dateKey) || summaryForDate(dateKey)
    ), [summariesByDate, summaryForDate]);

    const calendarReturnPath = useMemo(() => buildCalendarReturnPath({
        view: mode,
        anchor,
        employeeId,
        availability: availabilityFilter,
    }), [mode, anchor, employeeId, availabilityFilter]);

    const taskManagementUrl = useCallback((params) => {
        const query = new URLSearchParams({ ...params, from: "staff-calendar", returnTo: calendarReturnPath });
        return `/task-management?${query.toString()}`;
    }, [calendarReturnPath]);

    const goToTask = (task) => router.push(taskManagementUrl({
        tab: "tasks",
        taskId: String(task.id),
        ...(task.assigned_employee_id ? { employeeId: String(task.assigned_employee_id) } : {}),
        date: task.activity_date,
    }));
    const goToTasksForDate = (dateKey, rowEmployeeId = "") => router.push(taskManagementUrl({
        tab: "tasks",
        date: dateKey,
        ...(rowEmployeeId ? { employeeId: String(rowEmployeeId) } : {}),
    }));
    const goToCoverage = (dateKey) => router.push(taskManagementUrl({ tab: "tasks", assignmentState: "needs-reassignment", date: dateKey }));
    const goToLeave = (leave) => router.push(taskManagementUrl({ tab: "leave", leaveRequestId: String(leave.id) }));
    const goToEmployee = (employee) => router.push(taskManagementUrl({ tab: "employees", employeeId: String(employee.id) }));
    const closeDateDetails = useCallback(() => {
        if (actionBusyRef.current) return;
        setActionError("");
        setSelectedDate("");
        setEditor(null);
    }, []);

    const move = (direction) => {
        initialDateProvidedRef.current = true;
        closeDateDetails();
        setAnchor((current) => moveCalendarAnchor(current, mode, direction));
    };
    const goToday = () => {
        initialDateProvidedRef.current = true;
        closeDateDetails();
        setAnchor(todayKey);
    };
    const changeView = (nextMode) => {
        initialDateProvidedRef.current = true;
        closeDateDetails();
        setMode(nextMode);
    };
    const openDate = (dateKey) => {
        initialDateProvidedRef.current = true;
        closeDateDetails();
        setAnchor(dateKey);
        setMode("day");
    };

    const rememberDetailsFocus = () => {
        const active = document.activeElement;
        if (active instanceof HTMLElement && !detailsModalRef.current?.contains(active)) {
            previousFocusRef.current = active;
        }
    };

    useEffect(() => {
        if (!selectedDate || !portalReady) return undefined;

        if (!previousFocusRef.current?.isConnected) {
            previousFocusRef.current = document.activeElement instanceof HTMLElement
                ? document.activeElement
                : null;
        }

        window.dispatchEvent(new CustomEvent("joross:modal-open", {
            detail: { source: "staff-calendar" },
        }));

        const scrollbarGap = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
        const scrollY = window.scrollY;
        const previousHtmlOverflow = document.documentElement.style.overflow;
        const previousBodyStyles = {
            overflow: document.body.style.overflow,
            paddingRight: document.body.style.paddingRight,
            position: document.body.style.position,
            top: document.body.style.top,
            left: document.body.style.left,
            right: document.body.style.right,
            width: document.body.style.width,
        };

        document.documentElement.classList.add("calendar-modal-open");
        document.body.classList.add("calendar-modal-open");
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
        document.body.style.position = "fixed";
        document.body.style.top = `-${scrollY}px`;
        document.body.style.left = "0";
        document.body.style.right = "0";
        document.body.style.width = "100%";
        if (scrollbarGap > 0) document.body.style.paddingRight = `${scrollbarGap}px`;

        const focusTimer = window.setTimeout(() => {
            const modal = detailsModalRef.current;
            // A directly opened editor already focuses its first control.
            if (modal && !modal.contains(document.activeElement)) modal.focus({ preventScroll: true });
        }, 0);
        const handleKeyDown = (event) => {
            const modal = detailsModalRef.current;
            if (!modal) return;

            if (event.key === "Escape") {
                event.preventDefault();
                closeDateDetails();
                return;
            }

            if (event.key !== "Tab") return;

            const focusable = Array.from(modal.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
            )).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");

            if (!focusable.length) {
                event.preventDefault();
                modal.focus();
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            const active = document.activeElement;

            if (event.shiftKey && (active === first || !modal.contains(active))) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && (active === last || !modal.contains(active))) {
                event.preventDefault();
                first.focus();
            }
        };

        document.addEventListener("keydown", handleKeyDown, true);

        return () => {
            window.clearTimeout(focusTimer);
            document.removeEventListener("keydown", handleKeyDown, true);
            document.documentElement.classList.remove("calendar-modal-open");
            document.body.classList.remove("calendar-modal-open");
            document.documentElement.style.overflow = previousHtmlOverflow;
            Object.assign(document.body.style, previousBodyStyles);
            window.scrollTo(0, scrollY);

            const previousFocus = previousFocusRef.current;
            previousFocusRef.current = null;
            if (previousFocus?.isConnected) {
                window.requestAnimationFrame(() => previousFocus.focus({ preventScroll: true }));
            }
        };
    }, [selectedDate, portalReady, closeDateDetails]);

    const beginAttendanceView = (row) => {
        rememberDetailsFocus();
        setSelectedDate(row.dateKey);
        setEditor({ type: "view", employeeId: row.employee.id, dateKey: row.dateKey });
    };
    const showTodayAttendance = (filter = "all") => {
        openDate(todayKey);
        setAvailabilityFilter(filter);
        window.requestAnimationFrame(() => {
            calendarSectionRef.current?.scrollIntoView({ behavior: "instant", block: "start" });
            calendarSectionRef.current?.focus({ preventScroll: true });
        });
    };
    const beginAttendanceEdit = (row) => {
        if (!canManage || row.dateKey > todayKey) return;
        setActionError("");
        rememberDetailsFocus();
        setSelectedDate(row.dateKey);
        setAttendanceForm({
            employee_id: String(row.employee.id),
            attendance_date: row.dateKey,
            status: row.attendance?.status || "Present",
            notes: row.attendance?.notes || "",
            correction_reason: "",
        });
        setEditor({ type: "attendance", employeeId: row.employee.id, dateKey: row.dateKey });
    };

    const beginShiftEdit = (row, exceptionType = null) => {
        if (!canManageSchedule) return;
        setActionError("");
        rememberDetailsFocus();
        setSelectedDate(row.dateKey);
        setShiftForm({
            id: row.shift?.id || null,
            employee_id: String(row.employee.id),
            work_date: row.dateKey,
            start_time: row.shift?.start_time ? String(row.shift.start_time).slice(0, 5) : "",
            end_time: row.shift?.end_time ? String(row.shift.end_time).slice(0, 5) : "",
            assigned_area: row.shift?.assigned_area || row.employee.assigned_area || "",
            status: row.shift?.status || "Scheduled",
            notes: row.shift?.notes || "",
            exception_type: exceptionType ?? row.shift?.exception_type ?? "",
            exception_reason: row.shift?.exception_reason || "",
        });
        setEditor({ type: "shift", employeeId: row.employee.id, dateKey: row.dateKey });
    };

    const runAttendanceAction = async (action) => {
        if (actionBusyRef.current || !canManage || !editor || editor.dateKey > todayKey) return;
        const employee = Number(attendanceForm.employee_id);
        const workDate = attendanceForm.attendance_date;
        actionBusyRef.current = true;
        setActionError("");
        setAttendanceBusy(action);
        try {
            if (action === "check-in") await workforceService.assistedCheckIn(employee, attendanceForm.notes || null);
            else if (action === "check-out") await workforceService.assistedCheckOut(employee, attendanceForm.notes || null);
            else if (action === "absent") await workforceService.setAttendanceStatus(employee, workDate, "Absent", attendanceForm.notes || null);
            else if (action === "sick") await workforceService.setAttendanceStatus(employee, workDate, "Sick", attendanceForm.notes || null);
            actionBusyRef.current = false;
            setActionMessage("Attendance updated.");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            setActionError(err?.message || "Unable to record attendance. Please retry.");
        } finally {
            actionBusyRef.current = false;
            setAttendanceBusy("");
        }
    };

    const saveAttendance = async (event) => {
        event.preventDefault();
        if (actionBusyRef.current || !canManage || !editor || editor.dateKey > todayKey) return;
        if (!attendanceForm.correction_reason.trim()) {
            setActionError("A correction reason is required.");
            return;
        }
        actionBusyRef.current = true;
        setActionError("");
        setAttendanceBusy("correction");
        try {
            await workforceService.correctAttendance(
                Number(attendanceForm.employee_id),
                attendanceForm.attendance_date,
                { status: attendanceForm.status, notes: attendanceForm.notes || null, correction_reason: attendanceForm.correction_reason },
            );
            actionBusyRef.current = false;
            setActionMessage("Attendance correction saved with audit history.");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            setActionError(err?.message || "Unable to correct attendance. Please retry.");
        } finally {
            actionBusyRef.current = false;
            setAttendanceBusy("");
        }
    };

    const saveShift = async (event) => {
        event.preventDefault();
        if (actionBusyRef.current || !canManageSchedule) return;
        actionBusyRef.current = true;
        setActionError("");
        setAttendanceBusy("shift");
        const payload = {
            employee_id: Number(shiftForm.employee_id),
            work_date: shiftForm.work_date,
            start_time: shiftForm.start_time || null,
            end_time: shiftForm.end_time || null,
            assigned_area: shiftForm.assigned_area || null,
            status: shiftForm.status,
            notes: shiftForm.notes || null,
            exception_type: shiftForm.exception_type || null,
            exception_reason: shiftForm.exception_reason || null,
        };
        if (["Rest Day Override", "Special Day Off"].includes(shiftForm.exception_type)) {
            payload.start_time = null;
            payload.end_time = null;
        }
        try {
            if (shiftForm.id) await workforceService.updateShift(shiftForm.id, payload);
            else await workforceService.createShift(payload);
            actionBusyRef.current = false;
            setActionMessage(shiftForm.id ? "Roster shift updated." : "Roster shift added.");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            setActionError(err?.message || "Unable to save roster shift. Please retry.");
        } finally {
            actionBusyRef.current = false;
            setAttendanceBusy("");
        }
    };

    const requestWorkingDayOverride = canManageSchedule ? () => {
        const employee = employees.find((item) => Number(item.id) === Number(editor?.employeeId));
        if (employee && editor) beginShiftEdit(employeeDayRow(employee, editor.dateKey), "Working Day Override");
    } : undefined;

    return (
        <div className="workforce-layout">
            <Sidebar />
            <main className="workforce-page staff-calendar-page">
                <header className="workforce-header">
                    <div className="workforce-heading">
                        <h1>Staff Calendar</h1>
                        <p>
                            Workforce availability, attendance, roster shifts, leave, and task coverage in
                            {` ${farmTimezone}`}.
                        </p>
                    </div>
                    <div className="workforce-actions"><AppHeaderActions /></div>
                </header>

                {actionMessage && <p className="staff-calendar-save-message" role="status">{actionMessage}</p>}
                <StaffAttendanceSummary todayKey={todayKey} timezone={farmTimezone} summary={todaySummary}
                    ready={todayReady} busy={(loading || refreshing || !configReady) && !configError && !employeesError}
                    error={configError || employeesError || todayError} updatedAt={todayData?.updatedAt}
                    employeeName={employeeId ? selectedEmployees[0]?.full_name || "No matching employee" : ""}
                    onRefresh={refreshCalendar} onViewToday={() => showTodayAttendance()}
                    onFilter={showTodayAttendance} onViewRow={beginAttendanceView} onTask={goToTask} />

                <StaffCalendarToolbar
                    activeEmployees={activeEmployees}
                    anchor={anchor}
                    availabilityFilter={availabilityFilter}
                    changeView={changeView}
                    employeeId={employeeId}
                    goToday={goToday}
                    mode={mode}
                    move={move}
                    setAnchor={(date) => { initialDateProvidedRef.current = true; setAnchor(date); }}
                    setAvailabilityFilter={setAvailabilityFilter}
                    setEmployeeId={setEmployeeId}
                    closeEditor={closeDateDetails}
                    onClearFilters={() => { setEmployeeId(""); setAvailabilityFilter("all"); closeDateDetails(); }}
                    openFarmEvents={() => { closeDateDetails(); setEventPanel({}); }}
                />

                <section id="staff-calendar-content" className="staff-calendar-shell" ref={calendarSectionRef} tabIndex={-1} aria-label="Selected calendar dates">
                    <StaffCalendarHeading anchor={anchor} mode={mode} range={range} todayKey={todayKey} />
                    <p className="staff-attendance-freshness" role="status">{loading || refreshing ? "Updating calendar…" : error ? "Calendar could not be updated." : updatedAt ? `Calendar updated ${new Intl.DateTimeFormat("en-GB", { timeZone: farmTimezone, hour: "2-digit", minute: "2-digit" }).format(new Date(updatedAt))} (farm time)` : ""}</p>
                    {(error || employeesError || configError) && <div className="workforce-error" role="alert">Unable to load calendar. {error || employeesError || configError} <button type="button" className="workforce-button secondary compact" disabled={refreshing} onClick={refreshCalendar}>Retry calendar</button></div>}
                    {mode !== "month" && <CalendarEventBands events={data.farm_events || []} date={mode === "day" ? anchor : null} timezone={farmTimezone} onOpen={(id) => setEventPanel({ id })} />}
                    {(loading && !configError) || (!configReady && !configError) || (!employeesReady && !employeesError) ? (
                        <div className={`calendar-skeleton calendar-skeleton-${mode}`} aria-label="Loading calendar">
                            <span /><span /><span /><span /><span /><span />
                        </div>
                    ) : loadedRange !== rangeKey || error || employeesError || configError ? <p className="workforce-empty">Attendance and staffing totals are unavailable. Please retry.</p> : (
                        <StaffCalendarViews
                            events={data.farm_events || []}
                            timezone={farmTimezone}
                            openEvent={(id) => setEventPanel({ id })}
                            anchor={anchor}
                            availabilityFilter={availabilityFilter}
                            beginAttendanceView={beginAttendanceView}
                            beginShiftEdit={beginShiftEdit}
                            canManageSchedule={canManageSchedule}
                            days={days}
                            employeeDayRow={employeeDayRow}
                            employeeNames={employeeNames}
                            goToCoverage={goToCoverage}
                            goToEmployee={goToEmployee}
                            goToLeave={goToLeave}
                            goToTask={goToTask}
                            goToTasksForDate={goToTasksForDate}
                            mode={mode}
                            openDate={openDate}
                            rowsForDate={rowsForDate}
                            selectedEmployees={selectedEmployees}
                            summaryForDate={summaryForDisplay}
                            todayKey={todayKey}
                        />
                    )}
                </section>

                {eventPanel && <FarmEventPanel date={anchor} timezone={farmTimezone} initial={eventPanel.initial} initialId={eventPanel.id} events={data.farm_events || []} employees={activeEmployees} canManage={canManageSchedule} onClose={() => setEventPanel(null)} onChanged={() => loadCalendar({ background: true })} />}
                <StaffCalendarDetailsModal
                    attendanceBusy={attendanceBusy}
                    actionError={actionError} canManage={canManage} farmTimezone={farmTimezone}
                    row={editor ? staffDayRow(editorIndex, employees.find((item) => Number(item.id) === Number(editor.employeeId)) || {}, editor.dateKey, todayKey) : null}
                    onReviewAttendance={beginAttendanceEdit}
                    goToCoverage={goToCoverage}
                    goToLeave={goToLeave}
                    goToTask={goToTask}
                    goToTasksForDate={goToTasksForDate}
                    attendanceByEmployeeDate={editorIndex.attendance}
                    attendanceForm={attendanceForm}
                    availabilityByEmployeeDate={editorIndex.availability}
                    closeDateDetails={closeDateDetails}
                    detailsModalRef={detailsModalRef}
                    editor={editor}
                    employees={employees}
                    onRequestWorkingDayOverride={requestWorkingDayOverride}
                    portalReady={portalReady}
                    runAttendanceAction={runAttendanceAction}
                    saveAttendance={saveAttendance}
                    saveShift={saveShift}
                    selectedDate={selectedDate}
                    setAttendanceForm={setAttendanceForm}
                    setShiftForm={setShiftForm}
                    shiftForm={shiftForm}
                    todayKey={todayKey}
                />
            </main>
        </div>
    );
}

export default StaffCalendar;
