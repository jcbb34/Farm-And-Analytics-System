"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FarmEventPanel, CalendarEventBands } from "../../components/FarmEvents/FarmEvents.jsx";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { workforceService } from "../../services/workforceService.js";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { useNotification } from "../../context/NotificationContext.jsx";
import {
    DEFAULT_FARM_TIMEZONE,
    dateKeysBetween,
    farmDateKey,
    moveCalendarAnchor,
} from "../../utils/farmCalendar.js";
import {
    buildCalendarReturnPath,
    calendarDisplayRange,
    coverageState,
    employeeMatchesAvailabilityFilter,
    attendanceDisplayState,
    isActiveCalendarTask,
    isScheduledCalendarRow,
    isTemporarilyCoveredTask,
    leaveForEmployeeDate,
    normalizeAvailabilityFilter,
    normalizeCalendarView,
    taskNeedsCoverage,
} from "./staffCalendarView.js";
import StaffCalendarViews from "./StaffCalendarViews.jsx";
import StaffCalendarDetailsModal from "./StaffCalendarDetailsModal.jsx";
import { StaffCalendarHeading, StaffCalendarToolbar } from "./StaffCalendarToolbar.jsx";
import "./StaffCalendar.css";

const emptyCalendar = () => ({ tasks: [], attendance: [], leave: [], shifts: [], availability: [] });

function StaffCalendar() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { hasPermission } = useAuth();
    const notification = useNotification();
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

    useEffect(() => {
        let cancelled = false;
        workforceService.getCalendarConfig()
            .then((config) => {
                if (cancelled || !config) return;
                const nextTimezone = config.timezone || DEFAULT_FARM_TIMEZONE;
                const nextToday = config.today || farmDateKey(new Date(), nextTimezone);
                setFarmTimezone(nextTimezone);
                setTodayKey(nextToday);
                if (!initialDateProvidedRef.current) setAnchor(nextToday);
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        if (!canManage) return;
        let cancelled = false;
        workforceService.getEmployees()
            .then((rows) => { if (!cancelled) setEmployees(rows || []); })
            .catch((err) => { if (!cancelled) notification.error(err?.message || "Unable to load employees.", "Calendar Error"); });
        return () => { cancelled = true; };
    }, [canManage, notification]);

    const loadCalendar = useCallback(async ({ background = false } = {}) => {
        const requestId = ++requestSequenceRef.current;
        if (background) setRefreshing(true);
        else setLoading(true);
        setError("");
        try {
            const calendar = await workforceService.getCalendar(range[0], range[1], null);
            if (requestId !== requestSequenceRef.current) return;
            setData(calendar || emptyCalendar());
        } catch (err) {
            if (requestId !== requestSequenceRef.current || err?.code === "REQUEST_ABORTED") return;
            const message = err?.message || "Unable to load staff calendar.";
            setError(message);
            notification.error(message, "Calendar Error");
        } finally {
            if (requestId === requestSequenceRef.current) {
                setLoading(false);
                setRefreshing(false);
            }
        }
    }, [range, notification]);

    useEffect(() => { loadCalendar(); }, [loadCalendar]);
    useFarmModuleUpdates(["calendar", "tasks", "employees"], () => loadCalendar({ background: true }), {
        editing: Boolean(editor || eventPanel),
    });

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

    const tasksByDate = useMemo(() => {
        const map = new Map();
        (data.tasks || []).forEach((task) => {
            if (!map.has(task.activity_date)) map.set(task.activity_date, []);
            map.get(task.activity_date).push(task);
        });
        return map;
    }, [data.tasks]);

    const attendanceByEmployeeDate = useMemo(() => new Map(
        (data.attendance || []).map((row) => [`${row.employee_id}:${row.attendance_date}`, row]),
    ), [data.attendance]);

    const shiftByEmployeeDate = useMemo(() => {
        const map = new Map();
        (data.shifts || []).forEach((row) => {
            if (row.status !== "Cancelled") map.set(`${row.employee_id}:${row.work_date}`, row);
        });
        return map;
    }, [data.shifts]);

    const availabilityByEmployeeDate = useMemo(() => new Map(
        (data.availability || []).map((row) => [`${row.employee_id}:${row.work_date}`, row]),
    ), [data.availability]);

    const selectedEmployees = useMemo(() => {
        if (!employeeId) return activeEmployees;
        return activeEmployees.filter((employee) => String(employee.id) === String(employeeId));
    }, [activeEmployees, employeeId]);

    const employeeDayRow = useCallback((employee, dateKey) => {
        const allTasks = (tasksByDate.get(dateKey) || []).filter((task) => (
            Number(task.assigned_employee_id) === Number(employee.id)
            || Number(task.original_employee_id) === Number(employee.id)
            || Number(task.covering_employee_id) === Number(employee.id)
        ));
        const assignedTasks = allTasks.filter((task) => Number(task.assigned_employee_id) === Number(employee.id) && isActiveCalendarTask(task));
        const attendance = attendanceByEmployeeDate.get(`${employee.id}:${dateKey}`) || null;
        const shift = shiftByEmployeeDate.get(`${employee.id}:${dateKey}`) || null;
        const leave = leaveForEmployeeDate(data.leave, employee.id, dateKey);
        const approvedLeave = leave.find((item) => item.status === "Approved") || null;
        const pendingLeave = leave.filter((item) => item.status === "Pending");
        const availability = availabilityByEmployeeDate.get(`${employee.id}:${dateKey}`) || null;
        const state = attendanceDisplayState({
            dateKey,
            todayKey,
            attendance,
            approvedLeave,
            shift,
            employee,
            availability,
            activeTaskCount: assignedTasks.length,
        });
        return { employee, dateKey, tasks: allTasks, assignedTasks, attendance, shift, availability, leave, approvedLeave, pendingLeave, state };
    }, [tasksByDate, attendanceByEmployeeDate, shiftByEmployeeDate, availabilityByEmployeeDate, data.leave, todayKey]);

    const rowsForDate = useCallback((dateKey) => selectedEmployees
        .map((employee) => employeeDayRow(employee, dateKey))
        .filter((row) => employeeMatchesAvailabilityFilter({ filter: availabilityFilter, state: row.state, tasks: row.tasks })),
    [selectedEmployees, employeeDayRow, availabilityFilter]);

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
        setSelectedDate("");
        setEditor(null);
    }, []);

    const move = (direction) => {
        closeDateDetails();
        setAnchor((current) => moveCalendarAnchor(current, mode, direction));
    };
    const goToday = () => {
        closeDateDetails();
        setAnchor(todayKey);
    };
    const changeView = (nextMode) => {
        closeDateDetails();
        setMode(nextMode);
    };
    const openDate = (dateKey) => {
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
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
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

    const beginAttendanceEdit = (row) => {
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
        if (attendanceBusy) return;
        const employee = Number(attendanceForm.employee_id);
        const workDate = attendanceForm.attendance_date;
        setAttendanceBusy(action);
        try {
            if (action === "check-in") await workforceService.assistedCheckIn(employee, attendanceForm.notes || null);
            else if (action === "check-out") await workforceService.assistedCheckOut(employee, attendanceForm.notes || null);
            else if (action === "absent") await workforceService.setAttendanceStatus(employee, workDate, "Absent", attendanceForm.notes || null);
            else if (action === "sick") await workforceService.setAttendanceStatus(employee, workDate, "Sick", attendanceForm.notes || null);
            notification.success("Attendance recorded using the farm server workflow.", "Attendance");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            notification.error(err?.message || "Unable to record attendance.", "Attendance Error");
        } finally {
            setAttendanceBusy("");
        }
    };

    const saveAttendance = async (event) => {
        event.preventDefault();
        if (attendanceBusy) return;
        if (!attendanceForm.correction_reason.trim()) {
            notification.error("A correction reason is required.", "Attendance Correction");
            return;
        }
        setAttendanceBusy("correction");
        try {
            await workforceService.correctAttendance(
                Number(attendanceForm.employee_id),
                attendanceForm.attendance_date,
                { status: attendanceForm.status, notes: attendanceForm.notes || null, correction_reason: attendanceForm.correction_reason },
            );
            notification.success("Attendance correction saved with audit history.", "Attendance");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            notification.error(err?.message || "Unable to correct attendance.", "Attendance Error");
        } finally {
            setAttendanceBusy("");
        }
    };

    const saveShift = async (event) => {
        event.preventDefault();
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
            notification.success(shiftForm.id ? "Roster shift updated." : "Roster shift added.", "Staff Roster");
            closeDateDetails();
            await loadCalendar({ background: true });
        } catch (err) {
            notification.error(err?.message || "Unable to save roster shift.", "Roster Error");
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

                {error && <div className="workforce-error" role="alert">{error} <button type="button" className="workforce-button secondary compact" disabled={refreshing} onClick={() => loadCalendar({ background: true })}>Retry</button></div>}

                <StaffCalendarToolbar
                    activeEmployees={activeEmployees}
                    anchor={anchor}
                    availabilityFilter={availabilityFilter}
                    changeView={changeView}
                    employeeId={employeeId}
                    goToday={goToday}
                    mode={mode}
                    move={move}
                    setAnchor={setAnchor}
                    setAvailabilityFilter={setAvailabilityFilter}
                    setEmployeeId={setEmployeeId}
                    closeEditor={closeDateDetails}
                    openFarmEvents={() => { closeDateDetails(); setEventPanel({}); }}
                />

                <section className="staff-calendar-shell">
                    <StaffCalendarHeading anchor={anchor} mode={mode} range={range} />
                    {mode !== "month" && <CalendarEventBands events={data.farm_events || []} date={mode === "day" ? anchor : null} timezone={farmTimezone} onOpen={(id) => setEventPanel({ id })} />}
                    {loading ? (
                        <div className={`calendar-skeleton calendar-skeleton-${mode}`} aria-label="Loading calendar">
                            <span /><span /><span /><span /><span /><span />
                        </div>
                    ) : (
                        <StaffCalendarViews
                            events={data.farm_events || []}
                            timezone={farmTimezone}
                            openEvent={(id) => setEventPanel({ id })}
                            anchor={anchor}
                            availabilityFilter={availabilityFilter}
                            beginAttendanceEdit={beginAttendanceEdit}
                            beginShiftEdit={beginShiftEdit}
                            canManage={canManage}
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
                    attendanceByEmployeeDate={attendanceByEmployeeDate}
                    attendanceForm={attendanceForm}
                    availabilityByEmployeeDate={availabilityByEmployeeDate}
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
