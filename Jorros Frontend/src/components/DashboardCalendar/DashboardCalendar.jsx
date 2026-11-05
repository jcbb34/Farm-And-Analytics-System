"use client";

import { eventCreatePath } from "../FarmEvents/eventView.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { notify } from "../../context/NotificationContext.jsx";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import FarmLocationInput from "../FarmLocationInput/FarmLocationInput.jsx";
import EventResourceFields from "./EventResourceFields.jsx";
import EventContextFields from "./EventContextFields.jsx";
import { WORK_TYPE_GROUPS, workTypeLabel, eventDomain, eventRecordChoices, eventRecordLocation } from "../../services/eventPlanning.js";
import { workforceService } from "../../services/workforceService.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../../services/idempotencyKey.js";
import { activeEventEmployees, eventNeedsResource, eventSourceModule } from "./eventFormHelpers.js";
import { activityService } from "../../services/activityService.js";

import "./DashboardCalendar.css";

const monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

const miniWeekDays = [
    "Mo",
    "Tu",
    "We",
    "Th",
    "Fr",
    "Sa",
    "Su",
];

const fullWeekDays = [
    "Sun",
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
];

function padNumber(number) {
    return String(number).padStart(2, "0");
}

function formatDateKey(date) {
    return [
        date.getFullYear(),
        padNumber(date.getMonth() + 1),
        padNumber(date.getDate()),
    ].join("-");
}

function parseDateKey(dateKey) {
    const [year, month, day] =
        dateKey.split("-").map(Number);

    return new Date(
        year,
        month - 1,
        day
    );
}


function eventIsInPeriod(dateKey, period) {
    if (!dateKey) {
        return false;
    }

    const eventDate = parseDateKey(
        String(dateKey).slice(0, 10)
    );

    if (Number.isNaN(eventDate.getTime())) {
        return false;
    }

    if (typeof period === "string" && period.includes(" to ")) {
        const [fromStr, toStr] = period.split(" to ");
        const fromDate = parseDateKey(fromStr);
        const toDate = parseDateKey(toStr);
        if (fromDate && toDate) {
            toDate.setHours(23, 59, 59, 999);
            return eventDate >= fromDate && eventDate <= toDate;
        }
    }

    const now = new Date();
    const start = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate()
    );
    const end = new Date(start);

    if (period === "week") {
        const day = start.getDay();
        start.setDate(
            start.getDate() +
                (day === 0 ? -6 : 1 - day)
        );
        end.setTime(start.getTime());
        end.setDate(end.getDate() + 6);
    } else if (period === "year") {
        start.setMonth(0, 1);
        end.setFullYear(start.getFullYear(), 11, 31);
    } else if (period === "month") {
        start.setDate(1);
        end.setFullYear(
            start.getFullYear(),
            start.getMonth() + 1,
            0
        );
    }

    return eventDate >= start && eventDate <= end;
}

function formatLongDate(date) {
    return date.toLocaleDateString(
        "en-US",
        {
            month: "long",
            day: "numeric",
            year: "numeric",
        }
    );
}

function formatShortDate(dateKey) {
    return parseDateKey(
        dateKey
    ).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
    });
}

function formatTime(timeValue) {
    if (!timeValue) {
        return "";
    }

    const [hourValue, minuteValue] =
        timeValue.split(":");

    const hour = Number(hourValue);
    const period = hour >= 12 ? "PM" : "AM";
    const displayHour = hour % 12 || 12;

    return `${displayHour}:${minuteValue} ${period}`;
}

function createEmptyEventForm(selectedDate) {
    return {
        title: "",
        type: "Planting",
        date: formatDateKey(selectedDate),
        startTime: "08:00",
        endTime: "09:00",
        priority: "Medium",
        assignedEmployeeId: "",
        sourceModule: "Crop",
        sourceRecordId: "",
        inventoryItemId: "",
        plannedQuantity: "",
        feedingSlot: "",
        location: "",
        description: "",
        status: "Pending",
    };
}

function activityToCalendarEvent(activity) {
    return {
        id: activity.id,
        activityCode: activity.activityCode,
        date: activity.date,
        title: activity.name,
        location: activity.location,
        startTime: activity.startTime,
        endTime: activity.endTime,
        type: activity.category,
        priority: activity.priority,
        assignedTo: activity.assignedTo,
        description: activity.description,
        status: activity.status,
        relatedTo: activity.relatedTo,
        assignedBy: activity.assignedBy,
    };
}

function createMonthDays(
    displayedMonth,
    weekStartsOnMonday
) {
    const year =
        displayedMonth.getFullYear();

    const month =
        displayedMonth.getMonth();

    const firstDate =
        new Date(year, month, 1);

    const firstDayNumber =
        firstDate.getDay();

    const offset =
        weekStartsOnMonday
            ? (firstDayNumber + 6) % 7
            : firstDayNumber;

    const startDate = new Date(
        year,
        month,
        1 - offset
    );

    return Array.from(
        {
            length: 42,
        },
        (_, index) => {
            const date =
                new Date(startDate);

            date.setDate(
                startDate.getDate() + index
            );

            return {
                date,
                dateKey: formatDateKey(date),
                isCurrentMonth:
                    date.getMonth() === month,
            };
        }
    );
}

function getWeekDates(selectedDate) {
    const startDate =
        new Date(selectedDate);

    startDate.setDate(
        selectedDate.getDate() -
            selectedDate.getDay()
    );

    return Array.from(
        {
            length: 7,
        },
        (_, index) => {
            const date =
                new Date(startDate);

            date.setDate(
                startDate.getDate() + index
            );

            return date;
        }
    );
}

function getEventColorClass(type) {
    if (type === "Irrigation") {
        return "blue";
    }

    if (
        type === "Harvesting" ||
        type === "Fertilization"
    ) {
        return "orange";
    }

    if (type === "Pest Control") {
        return "red";
    }

    if (
        type.includes("Livestock") ||
        type === "Vaccination"
    ) {
        return "purple";
    }

    if (
        type === "Equipment Maintenance" ||
        type === "Inventory Restocking"
    ) {
        return "yellow";
    }

    return "green";
}

function DashboardCalendar({ period = "month", eventCreationRequest = 0 }) {
    const { hasPermission, user } = useAuth();
    const canAssignEmployees = hasPermission("workforce:manage");
    const [eventEmployees, setEventEmployees] = useState([]), [employeesLoading, setEmployeesLoading] = useState(false);
    const [employeeError, setEmployeeError] = useState(""), [employeeRetry, setEmployeeRetry] = useState(0);
    const [existingEventTaskId, setExistingEventTaskId] = useState(null);
    const [eventResources, setEventResources] = useState({ crops: [], livestock: [], inventory: [] });
    const [resourcesLoading, setResourcesLoading] = useState(false), [resourceError, setResourceError] = useState("");
    const [resourceRetry, setResourceRetry] = useState(0), [eventSaving, setEventSaving] = useState(false);
    const eventSavingRef = useRef(false), eventRequestRef = useRef(null), eventDialogRef = useRef(null);
    const handledCreationRequestRef = useRef(0);

    const initialSelectedDate =
        new Date();

    const [
        currentMonth,
        setCurrentMonth,
    ] = useState(
        () =>
            new Date(
                initialSelectedDate.getFullYear(),
                initialSelectedDate.getMonth(),
                1
            )
    );

    const [
        selectedDate,
        setSelectedDate,
    ] = useState(initialSelectedDate);

    const [events, setEvents] =
        useState([]);

    const [calendarLoading, setCalendarLoading] =
        useState(true);

    const [calendarError, setCalendarError] =
        useState("");

    const [
        showFullCalendar,
        setShowFullCalendar,
    ] = useState(false);

    const [
        showEventModal,
        setShowEventModal,
    ] = useState(false);

    const [
        fullCalendarView,
        setFullCalendarView,
    ] = useState("Month");

    const [
        eventForm,
        setEventForm,
    ] = useState(() =>
        createEmptyEventForm(
            initialSelectedDate
        )
    );

    const needsResource = eventNeedsResource(eventForm);
    const selectedEventInventory = eventResources.inventory.find((item) => String(item.id) === String(eventForm.inventoryItemId));
    const eventTargets = eventRecordChoices(eventForm, eventResources);
    const selectedEventRecord = eventTargets.find((row) => String(row.id) === String(eventForm.sourceRecordId));
    const eventKind = eventDomain(eventForm.type);
    const inventoryPlan = eventKind === "Inventory";
    const eventLocationOptions = selectedEventRecord
        ? [eventRecordLocation(selectedEventRecord, eventForm.sourceModule)]
        : eventKind === "General" && !needsResource
            ? [...eventResources.crops.map((row) => row.field), ...eventResources.livestock.map((row) => row.location), ...eventResources.inventory.map((row) => row.location)]
            : eventTargets.map((row) => eventRecordLocation(row, eventForm.sourceModule));
    useEffect(() => {
        if (!showEventModal || !canAssignEmployees) return;
        let alive = true; setEmployeesLoading(true); setEmployeeError("");
        workforceService.getEmployees().then((rows) => { if (alive) setEventEmployees(activeEventEmployees(rows)); })
            .catch((error) => { if (alive) { setEventEmployees([]); setEmployeeError(error?.message || "Unable to load employees."); } })
            .finally(() => { if (alive) setEmployeesLoading(false); });
        return () => { alive = false; };
    }, [showEventModal, canAssignEmployees, employeeRetry]);
    useEffect(() => {
        if (!showEventModal) return;
        const controller = new AbortController(); let alive = true; setResourcesLoading(true); setResourceError("");
        activityService.getEventResources(controller.signal).then((data) => {
            if (alive) setEventResources({ crops: Array.isArray(data?.crops) ? data.crops : [], livestock: Array.isArray(data?.livestock) ? data.livestock : [], inventory: Array.isArray(data?.inventory) ? data.inventory : [] });
        }).catch((error) => { if (alive) setResourceError(error?.message || "Unable to load linked work choices."); })
            .finally(() => { if (alive) setResourcesLoading(false); });
        return () => { alive = false; controller.abort(); };
    }, [showEventModal, resourceRetry]);

    const loadCalendarActivities = useCallback(
        async () => {
            try {
                setCalendarLoading(true);
                setCalendarError("");

                const records =
                    await activityService.getActivities(false);

                setEvents(
                    records.map(
                        activityToCalendarEvent
                    )
                );
            } catch (error) {
                console.error(
                    "Failed to load calendar activities:",
                    error
                );

                setCalendarError(
                    error?.message ||
                        "Unable to load calendar activities."
                );
            } finally {
                setCalendarLoading(false);
            }
        },
        []
    );

    useEffect(() => {
        loadCalendarActivities();

        const refreshActivities = () => {
            loadCalendarActivities();
        };

        window.addEventListener(
            "joross:activities-updated",
            refreshActivities
        );

        return () => {
            window.removeEventListener(
                "joross:activities-updated",
                refreshActivities
            );
        };
    }, [loadCalendarActivities]);

    // Changing the dashboard period brings the calendar back to the current date.
    useEffect(() => {
        const today = new Date();

        setSelectedDate(today);
        setCurrentMonth(
            new Date(
                today.getFullYear(),
                today.getMonth(),
                1
            )
        );

        if (period === "today") {
            setFullCalendarView("Day");
        } else if (period === "week") {
            setFullCalendarView("Week");
        } else if (period === "year") {
            setFullCalendarView("Agenda");
        } else {
            setFullCalendarView("Month");
        }
    }, [period]);

    useEffect(() => {
        const shouldLockScroll =
            showFullCalendar ||
            showEventModal;

        if (shouldLockScroll) {
            document.body.style.overflow =
                "hidden";
        } else {
            document.body.style.overflow =
                "";
        }

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [
        showFullCalendar,
        showEventModal,
    ]);

    const miniCalendarDays =
        useMemo(
            () =>
                createMonthDays(
                    currentMonth,
                    true
                ),
            [currentMonth]
        );

    const fullCalendarDays =
        useMemo(
            () =>
                createMonthDays(
                    currentMonth,
                    false
                ),
            [currentMonth]
        );

    // Only events inside the dashboard's selected period are shown.
    const visibleEvents = useMemo(
        () =>
            events.filter((farmEvent) =>
                eventIsInPeriod(
                    farmEvent.date,
                    period
                )
            ),
        [events, period]
    );

    const selectedDateKey =
        formatDateKey(selectedDate);

    const selectedEvents =
        useMemo(
            () =>
                visibleEvents
                    .filter(
                        (event) =>
                            event.date ===
                            selectedDateKey
                    )
                    .sort((first, second) =>
                        first.startTime.localeCompare(
                            second.startTime
                        )
                    ),
            [visibleEvents, selectedDateKey]
        );

    const upcomingEvents =
        useMemo(() => {
            const selectedStart =
                new Date(
                    selectedDate.getFullYear(),
                    selectedDate.getMonth(),
                    selectedDate.getDate()
                );

            return visibleEvents
                .filter((event) => {
                    const eventDate =
                        parseDateKey(
                            event.date
                        );

                    const difference =
                        Math.round(
                            (eventDate -
                                selectedStart) /
                                86400000
                        );

                    return (
                        difference > 0 &&
                        difference <= 7
                    );
                })
                .sort(
                    (first, second) =>
                        first.date.localeCompare(
                            second.date
                        ) ||
                        first.startTime.localeCompare(
                            second.startTime
                        )
                );
        }, [visibleEvents, selectedDate]);

    const weekDates =
        useMemo(
            () =>
                getWeekDates(
                    selectedDate
                ),
            [selectedDate]
        );

    const sortedAgendaEvents =
        useMemo(
            () =>
                [...visibleEvents].sort(
                    (first, second) =>
                        first.date.localeCompare(
                            second.date
                        ) ||
                        first.startTime.localeCompare(
                            second.startTime
                        )
                ),
            [visibleEvents]
        );

    const calendarSummary =
        useMemo(
            () => ({
                total: visibleEvents.length,

                harvests: visibleEvents.filter(
                    (event) =>
                        event.type ===
                        "Harvesting"
                ).length,

                livestock: visibleEvents.filter(
                    (event) =>
                        event.type.includes(
                            "Livestock"
                        ) ||
                        event.type ===
                            "Vaccination"
                ).length,

                completed: visibleEvents.filter(
                    (event) =>
                        event.status ===
                        "Completed"
                ).length,
            }),
            [visibleEvents]
        );

    const goToPreviousMonth = () => {
        setCurrentMonth(
            (previousMonth) =>
                new Date(
                    previousMonth.getFullYear(),
                    previousMonth.getMonth() -
                        1,
                    1
                )
        );
    };

    const goToNextMonth = () => {
        setCurrentMonth(
            (previousMonth) =>
                new Date(
                    previousMonth.getFullYear(),
                    previousMonth.getMonth() +
                        1,
                    1
                )
        );
    };

    const goToToday = () => {
        const today = new Date();

        setSelectedDate(today);

        setCurrentMonth(
            new Date(
                today.getFullYear(),
                today.getMonth(),
                1
            )
        );
    };

    const selectCalendarDate = (
        calendarDay
    ) => {
        setSelectedDate(
            calendarDay.date
        );

        if (
            !calendarDay.isCurrentMonth
        ) {
            setCurrentMonth(
                new Date(
                    calendarDay.date.getFullYear(),
                    calendarDay.date.getMonth(),
                    1
                )
            );
        }
    };

    const openAddEventModal = useCallback((
        date = selectedDate
    ) => {
        clearStableIdempotencyKey(eventRequestRef);
        setEventForm(
            createEmptyEventForm(date)
        );

        setShowEventModal(true);
    }, [selectedDate]);

    useEffect(() => {
        if (!eventCreationRequest || handledCreationRequestRef.current === eventCreationRequest) return;
        handledCreationRequestRef.current = eventCreationRequest;
        openAddEventModal();
    }, [eventCreationRequest, openAddEventModal]);

    const closeAddEventModal = () => { if (!eventSavingRef.current) setShowEventModal(false); };
    useEffect(() => {
        if (!showEventModal) return;
        const previousFocus = document.activeElement, previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden"; eventDialogRef.current?.querySelector("input")?.focus();
        const onKey = (event) => {
            if (event.key === "Escape" && !eventSavingRef.current) setShowEventModal(false);
            if (event.key !== "Tab") return;
            const nodes = [...(eventDialogRef.current?.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]') || [])].filter((node) => node.getClientRects().length);
            const first = nodes[0], last = nodes.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        };
        document.addEventListener("keydown", onKey);
        return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", onKey); previousFocus?.focus?.(); };
    }, [showEventModal]);

    const handleFormChange = (
        event
    ) => {
        const {
            name,
            value,
            type,
            checked,
        } = event.target;

        setEventForm(
            (currentForm) => ({
                ...currentForm,

                [name]:
                    type === "checkbox"
                        ? checked
                        : value,
                ...(name === "assignedEmployeeId" && value ? { status: "Pending" } : {}),
            })
        );
    };

    const selectEventType = (
        eventType
    ) => {
        setEventForm(
            (currentForm) => ({
                ...currentForm,
                type: eventType,
                sourceModule: eventSourceModule(eventType), sourceRecordId: "", inventoryItemId: "", plannedQuantity: "", feedingSlot: "", location: "",
            })
        );
    };

    const handleEventSubmit = async (event) => {
        event.preventDefault();
        if (eventSavingRef.current) return;
        if (!eventForm.title.trim() || !eventForm.date || !eventForm.startTime) { notify("Please complete the required event fields."); return; }
        if (eventForm.endTime && eventForm.endTime <= eventForm.startTime) { notify("The end time must be later than the start time."); return; }
        const employee = eventEmployees.find((row) => String(row.id) === String(eventForm.assignedEmployeeId));
        if (eventForm.assignedEmployeeId && (!employee || employee.portal_assignment_ready === false)) { notify("Select an active employee with a linked login account."); return; }
        if (eventKind === "Inventory" && !selectedEventRecord) { notify("Select the inventory item to restock."); return; }
        if (needsResource && (!eventForm.sourceRecordId || !selectedEventInventory || Number(eventForm.plannedQuantity) <= 0)) { notify("Choose the crop/livestock, inventory resource and planned quantity for this work."); return; }
        if (needsResource && Number(eventForm.plannedQuantity) > Number(selectedEventInventory.quantity)) { notify("The planned quantity exceeds the available inventory stock."); return; }
        const location = eventForm.location.trim() || "Joross Farm", target = eventTargets.find((row) => String(row.id) === String(eventForm.sourceRecordId));
        const payload = { name: eventForm.title, category: eventForm.type, relatedTo: target?.name || location, location,
            description: eventForm.description, instructions: eventForm.description, date: eventForm.date, startTime: eventForm.startTime, endTime: eventForm.endTime,
            assignedBy: user?.fullName || user?.full_name || "Farm Manager", assignedTo: employee?.full_name || "Unassigned", assignedEmployeeId: employee?.id || null,
            requiresReview: Boolean(employee), requiresEvidence: Boolean(employee), status: employee ? "Pending" : eventForm.status, priority: eventForm.priority,
            feedingSlot: eventForm.feedingSlot || null,
            ...(target ? { sourceModule: eventForm.sourceModule, sourceType: inventoryPlan ? "inventory_restock_plan" : "manual_work", sourceRecordId: Number(eventForm.sourceRecordId), sourcePath: eventForm.sourceModule === "Crop" ? "/crops" : eventForm.sourceModule === "Livestock" ? "/livestock" : "/inventory" } : {}),
            ...(needsResource ? { plannedInventoryItemId: Number(eventForm.inventoryItemId), plannedQuantity: Number(eventForm.plannedQuantity), plannedUnit: selectedEventInventory.unit } : {}) };
        eventSavingRef.current = true; setEventSaving(true); setExistingEventTaskId(null);
        try {
            const key = stableIdempotencyKey(eventRequestRef, payload, "calendar-event"), saved = await activityService.createActivity(payload, key), newEvent = activityToCalendarEvent(saved);
            setEvents((rows) => [...rows.filter((row) => row.id !== newEvent.id), newEvent]);
            const date = parseDateKey(eventForm.date); setSelectedDate(date); setCurrentMonth(new Date(date.getFullYear(), date.getMonth(), 1));
            clearStableIdempotencyKey(eventRequestRef); setShowEventModal(false);
            notify(employee ? "Farm event saved and assigned. The employee can see it in My Tasks." : "Farm event saved successfully.");
        } catch (error) { setExistingEventTaskId(error?.details?.existingTaskId || null); notify(error?.message || "Unable to save the farm event. Your entries have been kept."); }
        finally { eventSavingRef.current = false; setEventSaving(false); }
    };

    const renderEventTime = (
        farmEvent
    ) => {
        const start =
            formatTime(
                farmEvent.startTime
            );

        const end =
            formatTime(
                farmEvent.endTime
            );

        return end
            ? `${start} - ${end}`
            : start;
    };

    const renderMonthView = () => (
        <div className="fc-calendar-grid">
            {fullWeekDays.map(
                (weekDay) => (
                    <div
                        className="fc-weekday"
                        key={weekDay}
                    >
                        {weekDay}
                    </div>
                )
            )}

            {fullCalendarDays.map(
                (calendarDay) => {
                    const dayEvents =
                        visibleEvents.filter(
                            (event) =>
                                event.date ===
                                calendarDay.dateKey
                        );

                    const isSelected =
                        calendarDay.dateKey ===
                        selectedDateKey;

                    return (
                        <button
                            type="button"
                            key={
                                calendarDay.dateKey
                            }
                            className={[
                                "fc-day-cell",

                                !calendarDay.isCurrentMonth
                                    ? "muted"
                                    : "",

                                isSelected
                                    ? "selected"
                                    : "",
                            ]
                                .filter(Boolean)
                                .join(" ")}
                            onClick={() =>
                                selectCalendarDate(
                                    calendarDay
                                )
                            }
                        >
                            <span className="fc-date">
                                {
                                    calendarDay.date.getDate()
                                }
                            </span>

                            {dayEvents.length >
                                0 && (
                                <div className="fc-dots">
                                    {dayEvents
                                        .slice(0, 4)
                                        .map(
                                            (
                                                farmEvent
                                            ) => (
                                                <span
                                                    key={
                                                        farmEvent.id
                                                    }
                                                    className={`fc-dot ${getEventColorClass(
                                                        farmEvent.type
                                                    )}`}
                                                />
                                            )
                                        )}
                                </div>
                            )}

                            {dayEvents.length >
                                4 && (
                                <small className="fc-more-events">
                                    +
                                    {dayEvents.length -
                                        4}
                                </small>
                            )}
                        </button>
                    );
                }
            )}
        </div>
    );

    const renderWeekView = () => (
        <div className="fc-week-view">
            {weekDates.map((date) => {
                const dateKey =
                    formatDateKey(date);

                const dayEvents =
                    visibleEvents.filter(
                        (event) =>
                            event.date ===
                            dateKey
                    );

                return (
                    <section
                        className="fc-week-column"
                        key={dateKey}
                    >
                        <button
                            type="button"
                            className={
                                dateKey ===
                                selectedDateKey
                                    ? "fc-week-column-header selected"
                                    : "fc-week-column-header"
                            }
                            onClick={() =>
                                setSelectedDate(
                                    date
                                )
                            }
                        >
                            <span>
                                {date.toLocaleDateString(
                                    "en-US",
                                    {
                                        weekday:
                                            "short",
                                    }
                                )}
                            </span>

                            <strong>
                                {date.getDate()}
                            </strong>
                        </button>

                        <div className="fc-week-events">
                            {dayEvents.length >
                            0 ? (
                                dayEvents.map(
                                    (
                                        farmEvent
                                    ) => (
                                        <div
                                            className={`fc-week-event ${getEventColorClass(
                                                farmEvent.type
                                            )}`}
                                            key={
                                                farmEvent.id
                                            }
                                        >
                                            <strong>
                                                {
                                                    farmEvent.title
                                                }
                                            </strong>

                                            <small>
                                                {formatTime(
                                                    farmEvent.startTime
                                                )}
                                            </small>
                                        </div>
                                    )
                                )
                            ) : (
                                <span className="fc-week-empty">
                                    No events
                                </span>
                            )}
                        </div>
                    </section>
                );
            })}
        </div>
    );

    const renderDayView = () => (
        <div className="fc-day-view">
            <div className="fc-day-view-header">
                <span className="material-symbols-outlined">
                    today
                </span>

                <div>
                    <h3>
                        {formatLongDate(
                            selectedDate
                        )}
                    </h3>

                    <p>
                        {
                            selectedEvents.length
                        }{" "}
                        {selectedEvents.length ===
                        1
                            ? "scheduled event"
                            : "scheduled events"}
                    </p>
                </div>
            </div>

            <div className="fc-day-event-list">
                {selectedEvents.length >
                0 ? (
                    selectedEvents.map(
                        (farmEvent) => (
                            <div
                                className={`fc-day-event ${getEventColorClass(
                                    farmEvent.type
                                )}`}
                                key={
                                    farmEvent.id
                                }
                            >
                                <div>
                                    <strong>
                                        {
                                            farmEvent.title
                                        }
                                    </strong>

                                    <p>
                                        {
                                            farmEvent.location
                                        }
                                    </p>

                                    <small>
                                        {
                                            farmEvent.description
                                        }
                                    </small>
                                </div>

                                <span>
                                    {renderEventTime(
                                        farmEvent
                                    )}
                                </span>
                            </div>
                        )
                    )
                ) : (
                    <div className="fc-empty large">
                        No events scheduled
                        for this date.
                    </div>
                )}
            </div>
        </div>
    );

    const renderAgendaView = () => (
        <div className="fc-agenda-view">
            <div className="fc-agenda-header">
                <h3>Farm Agenda</h3>

                <span>
                    {sortedAgendaEvents.length}{" "}
                    events
                </span>
            </div>

            <div className="fc-agenda-list">
                {sortedAgendaEvents.map(
                    (farmEvent) => (
                        <button
                            type="button"
                            className="fc-agenda-item"
                            key={farmEvent.id}
                            onClick={() => {
                                const eventDate =
                                    parseDateKey(
                                        farmEvent.date
                                    );

                                setSelectedDate(
                                    eventDate
                                );

                                setCurrentMonth(
                                    new Date(
                                        eventDate.getFullYear(),
                                        eventDate.getMonth(),
                                        1
                                    )
                                );
                            }}
                        >
                            <div className="fc-agenda-date">
                                <strong>
                                    {formatShortDate(
                                        farmEvent.date
                                    )}
                                </strong>

                                <small>
                                    {formatTime(
                                        farmEvent.startTime
                                    )}
                                </small>
                            </div>

                            <span
                                className={`fc-upcoming-dot ${getEventColorClass(
                                    farmEvent.type
                                )}`}
                            />

                            <div className="fc-agenda-content">
                                <strong>
                                    {
                                        farmEvent.title
                                    }
                                </strong>

                                <small>
                                    {
                                        farmEvent.location
                                    }
                                </small>
                            </div>

                            <span
                                className={`fc-badge ${farmEvent.status
                                    .toLowerCase()
                                    .replace(
                                        " ",
                                        "-"
                                    )}`}
                            >
                                {
                                    farmEvent.status
                                }
                            </span>
                        </button>
                    )
                )}
            </div>
        </div>
    );

    const renderFullView = () => {
        if (
            fullCalendarView === "Week"
        ) {
            return renderWeekView();
        }

        if (
            fullCalendarView === "Day"
        ) {
            return renderDayView();
        }

        if (
            fullCalendarView ===
            "Agenda"
        ) {
            return renderAgendaView();
        }

        return renderMonthView();
    };

    return (
        <>
            <article className="dashboard-card calendar-card">
                <div className="calendar-layout">
                    <div className="mini-calendar">
                        <div className="calendar-month">
                            <button
                                type="button"
                                className="calendar-nav-button"
                                onClick={
                                    goToPreviousMonth
                                }
                                aria-label="Previous month"
                            >
                                <span className="material-symbols-outlined">
                                    chevron_left
                                </span>
                            </button>

                            <h4>
                                {
                                    monthNames[
                                        currentMonth.getMonth()
                                    ]
                                }
                            </h4>

                            <button
                                type="button"
                                className="calendar-nav-button"
                                onClick={
                                    goToNextMonth
                                }
                                aria-label="Next month"
                            >
                                <span className="material-symbols-outlined">
                                    chevron_right
                                </span>
                            </button>
                        </div>

                        <div className="calendar-weekdays">
                            {miniWeekDays.map(
                                (weekDay) => (
                                    <span
                                        key={
                                            weekDay
                                        }
                                    >
                                        {
                                            weekDay
                                        }
                                    </span>
                                )
                            )}
                        </div>

                        <div className="calendar-days">
                            {miniCalendarDays.map(
                                (
                                    calendarDay
                                ) => {
                                    const hasEvents =
                                        visibleEvents.some(
                                            (
                                                farmEvent
                                            ) =>
                                                farmEvent.date ===
                                                calendarDay.dateKey
                                        );

                                    const isSelected =
                                        calendarDay.dateKey ===
                                        selectedDateKey;

                                    return (
                                        <button
                                            type="button"
                                            key={
                                                calendarDay.dateKey
                                            }
                                            className={[
                                                "calendar-day",

                                                !calendarDay.isCurrentMonth
                                                    ? "muted"
                                                    : "",

                                                isSelected
                                                    ? "active-day"
                                                    : "",

                                                hasEvents
                                                    ? "has-event"
                                                    : "",
                                            ]
                                                .filter(
                                                    Boolean
                                                )
                                                .join(
                                                    " "
                                                )}
                                            onClick={() =>
                                                selectCalendarDate(
                                                    calendarDay
                                                )
                                            }
                                        >
                                            {
                                                calendarDay.date.getDate()
                                            }
                                        </button>
                                    );
                                }
                            )}
                        </div>
                    </div>

                    <div className="today-events">
                        <div className="event-header">
                            <div>
                                <h3>
                                    {formatLongDate(
                                        selectedDate
                                    )}
                                </h3>

                                <span>
                                    {selectedEvents.length > 3
                                        ? `3 of ${selectedEvents.length} Events`
                                        : `${selectedEvents.length} ${
                                              selectedEvents.length === 1
                                                  ? "Event"
                                                  : "Events"
                                          }`}
                                </span>
                            </div>

                            <button
                                type="button"
                                className="calendar-icon"
                                aria-label="Open full calendar"
                                onClick={() =>
                                    setShowFullCalendar(
                                        true
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    calendar_month
                                </span>
                            </button>
                        </div>

                        <hr />

                        <div className="selected-event-list">
                            {selectedEvents.length >
                            0 ? (
                                selectedEvents
                                    .slice(0, 3)
                                    .map(
                                    (
                                        farmEvent
                                    ) => (
                                        <div
                                            className="calendar-event-item"
                                            key={
                                                farmEvent.id
                                            }
                                        >
                                            <span
                                                className={`calendar-event-dot ${getEventColorClass(
                                                    farmEvent.type
                                                )}`}
                                            />

                                            <div>
                                                <strong>
                                                    {
                                                        farmEvent.title
                                                    }
                                                </strong>

                                                <p>
                                                    {
                                                        farmEvent.location
                                                    }
                                                </p>

                                                <small>
                                                    {renderEventTime(
                                                        farmEvent
                                                    )}
                                                </small>
                                            </div>
                                        </div>
                                    )
                                )
                            ) : (
                                <div className="calendar-empty-events">
                                    <span className="material-symbols-outlined">
                                        event_busy
                                    </span>

                                    <p>
                                        No events
                                        scheduled for
                                        this date.
                                    </p>
                                </div>
                            )}
                        </div>

                        <hr />

                        <div className="calendar-buttons">
                            <button
                                type="button"
                                className="calendar-view-button"
                                onClick={() =>
                                    setShowFullCalendar(
                                        true
                                    )
                                }
                            >
                                View Calendar
                            </button>

                            <button
                                type="button"
                                className="btn-green"
                                onClick={() =>
                                    openAddEventModal()
                                }
                            >
                                + Add Event
                            </button>
                        </div>
                    </div>
                </div>
            </article>

            {showFullCalendar && (
                <div
                    className="fc-overlay"
                    onMouseDown={() =>
                        setShowFullCalendar(
                            false
                        )
                    }
                >
                    <div
                        className="fc-modal"
                        onMouseDown={(
                            event
                        ) =>
                            event.stopPropagation()
                        }
                    >
                        <header className="fc-header">
                            <div className="fc-title">
                                <h2>
                                    Farm Calendar
                                </h2>

                                <p>
                                    View and manage
                                    farm activities,
                                    schedules, and
                                    events.
                                </p>
                            </div>

                            <button
                                type="button"
                                className="fc-close"
                                onClick={() =>
                                    setShowFullCalendar(
                                        false
                                    )
                                }
                                aria-label="Close full calendar"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </header>

                        <div className="fc-toolbar">
                            <div className="fc-toolbar-left">
                                <button
                                    type="button"
                                    className="fc-btn"
                                    onClick={
                                        goToToday
                                    }
                                >
                                    Today
                                </button>

                                <button
                                    type="button"
                                    className="fc-btn icon"
                                    onClick={
                                        goToPreviousMonth
                                    }
                                    aria-label="Previous month"
                                >
                                    <span className="material-symbols-outlined">
                                        chevron_left
                                    </span>
                                </button>

                                <button
                                    type="button"
                                    className="fc-btn icon"
                                    onClick={
                                        goToNextMonth
                                    }
                                    aria-label="Next month"
                                >
                                    <span className="material-symbols-outlined">
                                        chevron_right
                                    </span>
                                </button>

                                <h3 className="fc-month-title">
                                    {
                                        monthNames[
                                            currentMonth.getMonth()
                                        ]
                                    }{" "}
                                    {
                                        currentMonth.getFullYear()
                                    }
                                </h3>
                            </div>

                            <div className="fc-toolbar-right">
                                <div className="fc-view-buttons">
                                    {[
                                        "Month",
                                        "Week",
                                        "Day",
                                        "Agenda",
                                    ].map(
                                        (
                                            view
                                        ) => (
                                            <button
                                                type="button"
                                                key={
                                                    view
                                                }
                                                className={
                                                    fullCalendarView ===
                                                    view
                                                        ? "active"
                                                        : ""
                                                }
                                                onClick={() =>
                                                    setFullCalendarView(
                                                        view
                                                    )
                                                }
                                            >
                                                {
                                                    view
                                                }
                                            </button>
                                        )
                                    )}
                                </div>

                                <button
                                    type="button"
                                    className="fc-add-btn"
                                    onClick={() =>
                                        openAddEventModal()
                                    }
                                >
                                    <span className="material-symbols-outlined">
                                        add
                                    </span>

                                    Add Event
                                </button>
                            </div>
                        </div>

                        <div className="fc-content">
                            <section className="fc-summary-section">
                                <h3>
                                    Farm Summary
                                </h3>

                                <div className="fc-summary-row">
                                    <div className="fc-summary-box green">
                                        <h4>
                                            Total
                                            Events
                                        </h4>

                                        <h2>
                                            {
                                                calendarSummary.total
                                            }
                                        </h2>
                                    </div>

                                    <div className="fc-summary-box blue">
                                        <h4>
                                            Harvests
                                        </h4>

                                        <h2>
                                            {
                                                calendarSummary.harvests
                                            }
                                        </h2>
                                    </div>

                                    <div className="fc-summary-box orange">
                                        <h4>
                                            Livestock
                                        </h4>

                                        <h2>
                                            {
                                                calendarSummary.livestock
                                            }
                                        </h2>
                                    </div>

                                    <div className="fc-summary-box purple">
                                        <h4>
                                            Completed
                                        </h4>

                                        <h2>
                                            {
                                                calendarSummary.completed
                                            }
                                        </h2>
                                    </div>
                                </div>
                            </section>

                            <div className="fc-layout">
                                <div className="fc-left">
                                    {renderFullView()}
                                </div>

                                <aside className="fc-right">
                                    <section className="fc-card">
                                        <div className="fc-card-header">
                                            <h3>
                                                Selected
                                                Day
                                            </h3>

                                            <span>
                                                {formatLongDate(
                                                    selectedDate
                                                )}
                                            </span>
                                        </div>

                                        <div className="fc-selected-list">
                                            {selectedEvents.length >
                                            0 ? (
                                                selectedEvents.map(
                                                    (
                                                        farmEvent
                                                    ) => (
                                                        <div
                                                            className={`fc-event-card ${getEventColorClass(
                                                                farmEvent.type
                                                            )}`}
                                                            key={
                                                                farmEvent.id
                                                            }
                                                        >
                                                            <div className="fc-event-top">
                                                                <div className="fc-event-title">
                                                                    <span
                                                                        className={`fc-event-dot ${getEventColorClass(
                                                                            farmEvent.type
                                                                        )}`}
                                                                    />

                                                                    <strong>
                                                                        {
                                                                            farmEvent.title
                                                                        }
                                                                    </strong>
                                                                </div>

                                                                <span
                                                                    className={`fc-badge ${farmEvent.status
                                                                        .toLowerCase()
                                                                        .replace(
                                                                            " ",
                                                                            "-"
                                                                        )}`}
                                                                >
                                                                    {
                                                                        farmEvent.status
                                                                    }
                                                                </span>
                                                            </div>

                                                            <small>
                                                                {
                                                                    farmEvent.location
                                                                }
                                                            </small>

                                                            <div className="fc-event-time">
                                                                <span className="material-symbols-outlined">
                                                                    schedule
                                                                </span>

                                                                {renderEventTime(
                                                                    farmEvent
                                                                )}
                                                            </div>
                                                        </div>
                                                    )
                                                )
                                            ) : (
                                                <div className="fc-empty">
                                                    No
                                                    events
                                                    scheduled
                                                    for this
                                                    date.
                                                </div>
                                            )}
                                        </div>
                                    </section>

                                    <section className="fc-card">
                                        <div className="fc-card-header">
                                            <h3>
                                                Upcoming
                                                Events
                                            </h3>

                                            <span>
                                                Next 7
                                                Days
                                            </span>
                                        </div>

                                        <div className="fc-upcoming-list">
                                            {upcomingEvents.length >
                                            0 ? (
                                                upcomingEvents.map(
                                                    (
                                                        farmEvent
                                                    ) => (
                                                        <button
                                                            type="button"
                                                            className="fc-upcoming-item"
                                                            key={
                                                                farmEvent.id
                                                            }
                                                            onClick={() => {
                                                                const eventDate =
                                                                    parseDateKey(
                                                                        farmEvent.date
                                                                    );

                                                                setSelectedDate(
                                                                    eventDate
                                                                );

                                                                setCurrentMonth(
                                                                    new Date(
                                                                        eventDate.getFullYear(),
                                                                        eventDate.getMonth(),
                                                                        1
                                                                    )
                                                                );
                                                            }}
                                                        >
                                                            <span
                                                                className={`fc-upcoming-dot ${getEventColorClass(
                                                                    farmEvent.type
                                                                )}`}
                                                            />

                                                            <div className="fc-upcoming-content">
                                                                <strong>
                                                                    {
                                                                        farmEvent.title
                                                                    }
                                                                </strong>

                                                                <small>
                                                                    {
                                                                        farmEvent.location
                                                                    }
                                                                </small>
                                                            </div>

                                                            <div className="fc-upcoming-date">
                                                                <strong>
                                                                    {formatShortDate(
                                                                        farmEvent.date
                                                                    )}
                                                                </strong>

                                                                <small>
                                                                    {formatTime(
                                                                        farmEvent.startTime
                                                                    )}
                                                                </small>
                                                            </div>
                                                        </button>
                                                    )
                                                )
                                            ) : (
                                                <div className="fc-empty">
                                                    No
                                                    upcoming
                                                    events.
                                                </div>
                                            )}
                                        </div>
                                    </section>
                                </aside>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {showEventModal && (
                <div
                    className="calendar-event-overlay"
                    onMouseDown={
                        closeAddEventModal
                    }
                >
                    <div
                        className="calendar-event-modal"
                        ref={eventDialogRef} role="dialog" aria-modal="true" aria-label="Add Farm Event"
                        onMouseDown={(
                            event
                        ) =>
                            event.stopPropagation()
                        }
                    >
                        <header className="calendar-modal-header">
                            <div>
                                <h2>
                                    Add Farm Event
                                </h2>

                                <p>
                                    Schedule and
                                    manage farm
                                    activities,
                                    tasks, and events.
                                </p>
                            </div>

                            <button
                                type="button"
                                className="calendar-modal-close"
                                onClick={
                                    closeAddEventModal
                                }
                                aria-label="Close event form"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </header>

                        <form
                            className="calendar-event-form"
                            onSubmit={
                                handleEventSubmit
                            }
                        >
                            {hasPermission("workforce:manage") && <div className="calendar-event-declaration-entry">
                                <p>For a planned day off or emergency suspension, review affected attendance and work in Staff Calendar.</p>
                                <a className="workforce-button secondary" href={eventCreatePath({ date: eventForm.date, kind: "Planned No-Work Day" })}>Plan No-Work Day / Emergency</a>
                            </div>}
                            <div className="calendar-form-group">
                                <label htmlFor="eventTitle">
                                    Event Title
                                    <span className="required">
                                        *
                                    </span>
                                </label>

                                <input
                                    id="eventTitle"
                                    name="title"
                                    type="text"
                                    placeholder="Enter event title"
                                    value={
                                        eventForm.title
                                    }
                                    onChange={
                                        handleFormChange
                                    }
                                    required
                                />
                            </div>

                            <div className="calendar-form-group">
                                <label>
                                    Event Type
                                    <span className="required">
                                        *
                                    </span>
                                </label>

                                <div className="calendar-work-types">
                                    {WORK_TYPE_GROUPS.map((group) => (
                                        <div className="calendar-work-type-group" key={group.label} role="group" aria-label={`${group.label} event types`}>
                                            <span className="calendar-work-type-label">{group.label}</span>
                                            <div className="event-type-container">
                                                {group.types.map((eventType) => (
                                                    <button type="button" key={eventType}
                                                        className={eventForm.type === eventType ? "event-type-button active" : "event-type-button"}
                                                        aria-pressed={eventForm.type === eventType}
                                                        onClick={() => selectEventType(eventType)}>
                                                        {workTypeLabel(eventType)}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="calendar-form-row">
                                <div className="calendar-form-group">
                                    <label htmlFor="eventDate">
                                        Date
                                        <span className="required">
                                            *
                                        </span>
                                    </label>

                                    <input
                                        id="eventDate"
                                        name="date"
                                        type="date"
                                        value={
                                            eventForm.date
                                        }
                                        onChange={
                                            handleFormChange
                                        }
                                        required
                                    />
                                </div>

                                <div className="calendar-form-group">
                                    <label htmlFor="eventStartTime">
                                        Start Time
                                        <span className="required">
                                            *
                                        </span>
                                    </label>

                                    <input
                                        id="eventStartTime"
                                        name="startTime"
                                        type="time"
                                        value={
                                            eventForm.startTime
                                        }
                                        onChange={
                                            handleFormChange
                                        }
                                        required
                                    />
                                </div>

                                <div className="calendar-form-group">
                                    <label htmlFor="eventEndTime">
                                        End Time
                                    </label>

                                    <input
                                        id="eventEndTime"
                                        name="endTime"
                                        type="time"
                                        value={
                                            eventForm.endTime
                                        }
                                        onChange={
                                            handleFormChange
                                        }
                                    />
                                </div>
                            </div>

                            <div className="calendar-form-row two-columns">
                                <div className="calendar-form-group">
                                    <label htmlFor="eventPriority">
                                        Priority
                                    </label>

                                    <select
                                        id="eventPriority"
                                        name="priority"
                                        value={
                                            eventForm.priority
                                        }
                                        onChange={
                                            handleFormChange
                                        }
                                    >
                                        <option>
                                            Low
                                        </option>

                                        <option>
                                            Medium
                                        </option>

                                        <option>
                                            High
                                        </option>

                                        <option>
                                            Critical
                                        </option>
                                    </select>
                                </div>

                                <div className="calendar-form-group">
                                    <label htmlFor="eventStatus">
                                        Status
                                    </label>

                                    <select
                                        id="eventStatus"
                                        name="status"
                                        disabled={Boolean(eventForm.assignedEmployeeId) || eventSaving}
                                        value={
                                            eventForm.status
                                        }
                                        onChange={
                                            handleFormChange
                                        }
                                    >
                                        <option>
                                            Pending
                                        </option>

                                        <option>
                                            In Progress
                                        </option>

                                        <option>
                                            Completed
                                        </option>

                                        <option>
                                            Cancelled
                                        </option>
                                    </select>
                                </div>
                            </div>

                            {existingEventTaskId && <p role="status">This occurrence is already scheduled. <a href={`/task-management?taskId=${existingEventTaskId}`}>Open existing task</a></p>}
                            <EventContextFields form={eventForm} onChange={setEventForm} resources={eventResources} loading={resourcesLoading} error={resourceError} retry={() => setResourceRetry((old) => old + 1)} busy={eventSaving} needsResource={needsResource} />
                            <div className="calendar-form-row two-columns">
                                <div className="calendar-form-group">
                                    <label htmlFor="eventLocation">
                                        Location
                                    </label>

                                    <FarmLocationInput id="eventLocation" name="location" label="Location" context="events" eventType={eventForm.type} sourceModule={eventKind === "General" && !needsResource ? undefined : eventForm.sourceModule} sourceRecordId={eventForm.sourceRecordId} knownOptions={eventLocationOptions} readOnly={Boolean(selectedEventRecord)} active={showEventModal} value={eventForm.location} onValueChange={(location) => setEventForm((old) => ({ ...old, location }))} />
                                </div>

                                <div className="calendar-form-group">
                                    <label htmlFor="eventAssignedTo">
                                        Assigned To
                                    </label>

                                    <select id="eventAssignedTo" name="assignedEmployeeId" value={eventForm.assignedEmployeeId} disabled={!canAssignEmployees || employeesLoading || Boolean(employeeError) || eventSaving} onChange={handleFormChange}>
                                        <option value="">{employeesLoading ? "Loading employees…" : "No employee — calendar event only"}</option>
                                        {eventEmployees.map((employee) => <option key={employee.id} value={employee.id} disabled={employee.portal_assignment_ready === false}>{employee.full_name}{employee.portal_assignment_ready === false ? " — linked login required" : ""}</option>)}
                                    </select>
                                    {!canAssignEmployees && <small className="calendar-choice-hint">Employee assignment requires workforce management permission.</small>}
                                    {employeeError && <p className="calendar-choice-error" role="status">{employeeError} <button type="button" onClick={() => setEmployeeRetry((old) => old + 1)}>Retry employees</button></p>}
                                </div>
                            </div>

                            {needsResource && <EventResourceFields form={eventForm} onChange={setEventForm} resources={eventResources} loading={resourcesLoading} error={resourceError} retry={() => setResourceRetry((old) => old + 1)} busy={eventSaving} />}

                            <div className="calendar-form-group">
                                <label htmlFor="eventDescription">
                                    Description /
                                    Notes
                                </label>

                                <textarea
                                    id="eventDescription"
                                    name="description"
                                    rows="4"
                                    placeholder="Enter event details, instructions, or notes"
                                    value={
                                        eventForm.description
                                    }
                                    onChange={
                                        handleFormChange
                                    }
                                />
                            </div>

                            <p className="calendar-choice-hint">{eventForm.assignedEmployeeId ? "Assigned work starts as Pending and uses employee photo evidence, submission and manager approval." : "Unassigned events stay on the calendar. Select an employee to create assigned work in My Tasks."}</p>

                            <div className="calendar-modal-buttons">
                                <button
                                    type="button"
                                    className="calendar-cancel-button"
                                    onClick={
                                        closeAddEventModal
                                    }
                                >
                                    Cancel
                                </button>

                                <button
                                    type="submit"
                                    className="calendar-save-button"
                                    disabled={eventSaving || (Boolean(eventForm.assignedEmployeeId) && employeesLoading) || ((needsResource || eventKind === "Inventory") && resourcesLoading)}
                                >
                                    {eventSaving ? "Saving…" : "Save Event"}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </>
    );
}

export default DashboardCalendar;
