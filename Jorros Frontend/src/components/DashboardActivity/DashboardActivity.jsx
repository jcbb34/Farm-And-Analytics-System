"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { activityService } from "../../services/activityService.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import {
    activityRequiresTaskWorkflow,
    buildTaskManagementPath,
    resolveDashboardActivityActions,
} from "./dashboardActivityWorkflow.js";

import "./DashboardActivity.css";

// Categories available in the activity list filters
const categoryOptions = [
    "Planting",
    "Irrigation",
    "Fertilization",
    "Harvesting",
    "Pest Control",
    "Disease Treatment",
    "Livestock Feeding",
    "Livestock Health Check",
    "Vaccination",
    "Inventory Restocking",
    "Equipment Maintenance",
    "Farm Inspection",
    "Other",
];

// Small helpers for cleaner dates and times on the dashboard
function formatDate(dateValue) {
    if (!dateValue) {
        return "";
    }

    const [year, month, day] =
        dateValue.split("-").map(Number);

    return new Date(
        year,
        month - 1,
        day
    ).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
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


function getFeedingInventoryNotice(message) {
    const text = String(message || "").trim();
    const normalized = text.toLowerCase();

    const isFeedInventoryProblem =
        normalized.includes("feed inventory item") ||
        normalized.includes("not enough") ||
        normalized.includes("feeding cannot use") ||
        normalized.includes("insufficient feed");

    if (!isFeedInventoryProblem) {
        return null;
    }

    const needsLivestockLink =
        normalized.includes("no feed inventory item is linked") ||
        normalized.includes("link the correct feed item") ||
        normalized.includes("linked feed inventory item is missing");

    return {
        message: text,
        destination: needsLivestockLink
            ? "/livestock"
            : "/inventory",
        actionLabel: needsLivestockLink
            ? "Open Livestock Management"
            : "Go to Inventory",
        actionIcon: needsLivestockLink
            ? "pets"
            : "inventory_2",
    };
}

function goToPath(path) {
    if (typeof window === "undefined") {
        return;
    }

    window.location.assign(path);
}


function parseActivityDate(dateValue) {
    if (!dateValue) {
        return null;
    }

    const [year, month, day] =
        String(dateValue)
            .slice(0, 10)
            .split("-")
            .map(Number);

    if (!year || !month || !day) {
        return null;
    }

    return new Date(year, month - 1, day);
}


function activityIsInPeriod(dateValue, period) {
    const activityDate = parseActivityDate(dateValue);

    if (!activityDate) {
        return false;
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

    return activityDate >= start && activityDate <= end;
}

function getTaskDueMeta(dateValue) {
    const taskDate = parseActivityDate(dateValue);

    if (!taskDate) {
        return {
            label: "No date",
            className: "",
        };
    }

    const now = new Date();
    const today = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate()
    );

    const differenceDays = Math.round(
        (taskDate - today) / 86400000
    );

    if (differenceDays < 0) {
        return {
            label: "Overdue",
            className: "overdue",
        };
    }

    if (differenceDays === 0) {
        return {
            label: "Today",
            className: "today",
        };
    }

    if (differenceDays === 1) {
        return {
            label: "Tomorrow",
            className: "tomorrow",
        };
    }

    return {
        label: formatDate(dateValue),
        className: "",
    };
}

function DashboardActivity({ period = "month", onAddEvent }) {
    const notification = useNotification();
    const activityMutationRef = useRef(new Set());
    const [busyActivityIds, setBusyActivityIds] = useState(() => new Set());
    const [activities, setActivities] =
        useState([]);
    const locationOptions = useMemo(() => [...new Set(activities.map((activity) => activity.location).filter(Boolean))]
        .sort((left, right) => left.localeCompare(right)), [activities]);

    const [activitiesLoading, setActivitiesLoading] =
        useState(true);

    const [activitiesError, setActivitiesError] =
        useState("");

    const [activityModalOpen, setActivityModalOpen] =
        useState(false);

    const [taskModalOpen, setTaskModalOpen] =
        useState(false);

    const [activityFilters, setActivityFilters] =
        useState({
            search: "",
            category: "All",
            location: "All",
            status: "All",
            date: "",
            sort: "Latest",
        });

    const [taskSearch, setTaskSearch] =
        useState("");

    const [activityActionNotice, setActivityActionNotice] =
        useState(null);

    // Loads all active farm activities from the backend
    const loadActivities = useCallback(
        async ({ synchronize = false } = {}) => {
            try {
                setActivitiesLoading(true);
                setActivitiesError("");

                if (synchronize) {
                    try {
                        await activityService.syncAutomaticActivities();
                    } catch (syncError) {
                        console.warn(
                            "Unable to synchronize automatic farm activities before loading:",
                            syncError
                        );
                    }
                }

                const records =
                    await activityService.getActivities(false);

                setActivities(
                    records.filter(
                        (activity) => !activity.isArchived
                    )
                );
            } catch (error) {
                console.error(
                    "Failed to load farm activities:",
                    error
                );

                setActivitiesError(
                    error?.message ||
                        "Unable to load farm activities."
                );
            } finally {
                setActivitiesLoading(false);
            }
        },
        []
    );

    // Refresh this component when another part of the system updates activities
    useEffect(() => {
        loadActivities({ synchronize: true });

        const refreshActivities = () => {
            loadActivities();
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
    }, [loadActivities]);

    // Only active/completed work belongs in Recent Farm Activity
    const recentActivities = useMemo(
        () =>
            activities
                .filter(
                    (activity) =>
                        [
                            "In Progress",
                            "Completed",
                        ].includes(
                            activity.status
                        ) &&
                        activityIsInPeriod(
                            activity.date,
                            period
                        )
                )
                .sort((first, second) => {
                    const firstKey = `${String(
                        first.date || ""
                    ).slice(0, 10)}T${
                        first.startTime || "00:00"
                    }`;

                    const secondKey = `${String(
                        second.date || ""
                    ).slice(0, 10)}T${
                        second.startTime || "00:00"
                    }`;

                    return secondKey.localeCompare(
                        firstKey
                    );
                }),
        [activities, period]
    );

    // Pending activities are treated as upcoming tasks
    const tasks = useMemo(
        () =>
            activities
                .filter(
                    (activity) =>
                        activity.status === "Pending" &&
                        activityIsInPeriod(
                            activity.date,
                            period
                        )
                )
                .sort((first, second) => {
                    const firstKey = `${String(
                        first.date || ""
                    ).slice(0, 10)}T${
                        first.startTime || "00:00"
                    }`;

                    const secondKey = `${String(
                        second.date || ""
                    ).slice(0, 10)}T${
                        second.startTime || "00:00"
                    }`;

                    return firstKey.localeCompare(
                        secondKey
                    );
                })
                .map((activity) => ({
                    ...activity,
                    title: activity.name,
                    time: activity.startTime,
                })),
        [activities, period]
    );

    // Filters used inside the Recent Farm Activity modal
    const filteredActivities = useMemo(() => {
        const searchText =
            activityFilters.search
                .trim()
                .toLowerCase();

        const results = recentActivities.filter(
            (activity) => {
                const matchesSearch =
                    !searchText ||
                    String(activity.name || "")
                        .toLowerCase()
                        .includes(searchText) ||
                    String(activity.relatedTo || "")
                        .toLowerCase()
                        .includes(searchText) ||
                    String(activity.location || "")
                        .toLowerCase()
                        .includes(searchText);

                const matchesCategory =
                    activityFilters.category === "All" ||
                    activity.category ===
                        activityFilters.category;

                const matchesLocation =
                    activityFilters.location === "All" ||
                    activity.location ===
                        activityFilters.location;

                const matchesStatus =
                    activityFilters.status === "All" ||
                    activity.status ===
                        activityFilters.status;

                const matchesDate =
                    !activityFilters.date ||
                    String(activity.date || "").slice(
                        0,
                        10
                    ) === activityFilters.date;

                return (
                    matchesSearch &&
                    matchesCategory &&
                    matchesLocation &&
                    matchesStatus &&
                    matchesDate
                );
            }
        );

        return [...results].sort((first, second) => {
            if (activityFilters.sort === "Oldest") {
                return String(
                    first.date || ""
                ).localeCompare(
                    String(second.date || "")
                );
            }

            if (activityFilters.sort === "A - Z") {
                return String(
                    first.name || ""
                ).localeCompare(
                    String(second.name || "")
                );
            }

            if (activityFilters.sort === "Z - A") {
                return String(
                    second.name || ""
                ).localeCompare(
                    String(first.name || "")
                );
            }

            return String(
                second.date || ""
            ).localeCompare(
                String(first.date || "")
            );
        });
    }, [recentActivities, activityFilters]);

    const filteredTasks = useMemo(() => {
        const searchText =
            taskSearch.trim().toLowerCase();

        return tasks.filter((task) => {
            if (!searchText) {
                return true;
            }

            return (
                String(task.title || "")
                    .toLowerCase()
                    .includes(searchText) ||
                String(task.relatedTo || "")
                    .toLowerCase()
                    .includes(searchText) ||
                String(task.location || "")
                    .toLowerCase()
                    .includes(searchText)
            );
        });
    }, [tasks, taskSearch]);

    const handleActivityFilterChange = (event) => {
        const { name, value } = event.target;

        setActivityFilters((currentFilters) => ({
            ...currentFilters,
            [name]: value,
        }));
    };

    const openAddActivity = () => {
        setActivityModalOpen(false);
        setTaskModalOpen(false);
        onAddEvent?.();
    };

    // Keeps the backend and dashboard status in sync for the small set of
    // standalone activities the backend explicitly allows to mutate directly.
    // Workforce/task actions navigate into the authoritative task workflow.
    const updateActivityStatus = async (
        activityId,
        nextStatus
    ) => {
        if (activityMutationRef.current.has(activityId)) {
            return null;
        }

        const sourceActivity = activities.find(
            (activity) => activity.id === activityId
        );

        // Defense in depth for stale/cached Dashboard payloads: even if an older
        // API response incorrectly exposes a direct-complete action, never send
        // a raw PUT for an employee/workforce task. The backend remains the final
        // authority, but this prevents the repeated 400 requests seen in runtime
        // logs and routes the manager into the authoritative task workflow.
        if (
            nextStatus === "Completed" &&
            sourceActivity &&
            activityRequiresTaskWorkflow(sourceActivity)
        ) {
            const destination = buildTaskManagementPath(
                sourceActivity,
                "open_task"
            );
            const message =
                "This employee/workforce task must be completed through My Tasks and Task Management review.";
            setActivityActionNotice({
                activityId,
                activityName: sourceActivity?.name || "Task",
                message,
                destination,
                actionLabel: "Open Task",
                actionIcon: "open_in_new",
            });
            notification.error(message, "Task Workflow Required");
            return null;
        }

        activityMutationRef.current.add(activityId);
        setBusyActivityIds((current) => new Set([...current, activityId]));

        try {
            const updatedActivity =
                await activityService.updateActivity(
                    activityId,
                    {
                        status: nextStatus,
                    }
                );

            setActivities((currentActivities) =>
                updatedActivity.isArchived
                    ? currentActivities.filter(
                          (activity) =>
                              activity.id !== activityId
                      )
                    : currentActivities.map((activity) =>
                          activity.id === activityId
                              ? updatedActivity
                              : activity
                      )
            );

            setActivityActionNotice((currentNotice) =>
                currentNotice?.activityId === activityId
                    ? null
                    : currentNotice
            );

            notification.success(
                nextStatus === "Completed"
                    ? "Activity completed successfully."
                    : "Activity updated successfully.",
                "Farm Activity"
            );

            // activityService dispatches activities + alerts refresh events.
            // Do not issue a second explicit reload here; that used to create
            // duplicate GETs after every successful mutation.
            return updatedActivity;
        } catch (error) {
            const message = String(
                error?.message || ""
            );

            const feedingInventoryNotice =
                getFeedingInventoryNotice(message);

            if (feedingInventoryNotice) {
                const sourceActivity = activities.find(
                    (activity) => activity.id === activityId
                );

                setActivityActionNotice({
                    ...feedingInventoryNotice,
                    activityId,
                    activityName:
                        sourceActivity?.name ||
                        "Livestock feeding",
                });

                notification.error(message, "Activity Update");
                return null;
            }

            if (
                /employee\/workforce task|assisted submission|my tasks/i.test(
                    message
                )
            ) {
                const sourceActivity = activities.find(
                    (activity) => activity.id === activityId
                );
                const destination = buildTaskManagementPath(
                    sourceActivity || {
                        linkedTaskId: activityId,
                    },
                    "open_task"
                );
                setActivityActionNotice({
                    activityId,
                    activityName:
                        sourceActivity?.name || "Task",
                    message,
                    destination,
                    actionLabel: "Open Task",
                    actionIcon: "open_in_new",
                });
                notification.error(message, "Task Workflow Required");
                return null;
            }

            if (
                message
                    .toLowerCase()
                    .includes("archived farm activities cannot be modified")
            ) {
                setActivities((currentActivities) =>
                    currentActivities.filter(
                        (activity) =>
                            activity.id !== activityId
                    )
                );

                try {
                    await activityService.syncAutomaticActivities();
                } catch (syncError) {
                    console.warn(
                        "Unable to refresh replacement automatic activities:",
                        syncError
                    );
                }

                await loadActivities();
                return null;
            }

            console.error(
                "Failed to update activity status:",
                error
            );

            notification.error(
                error?.message ||
                    "Unable to update the activity status.",
                "Activity Update"
            );

            return null;
        } finally {
            activityMutationRef.current.delete(activityId);
            setBusyActivityIds((current) => {
                const next = new Set(current);
                next.delete(activityId);
                return next;
            });
        }
    };

    const startTask = async (activityId) => {
        await updateActivityStatus(
            activityId,
            "In Progress"
        );
    };

    const completeActivity = async (
        activityId
    ) => {
        await updateActivityStatus(
            activityId,
            "Completed"
        );
    };

    const runDashboardActivityAction = async (activity, action) => {
        if (!action || busyActivityIds.has(activity.id)) return;
        if (action.kind === "navigate") {
            goToPath(action.path);
            return;
        }
        if (action.kind === "start") {
            await startTask(activity.id);
            return;
        }
        if (action.kind === "complete") {
            await completeActivity(activity.id);
        }
    };

    const renderActivityActions = (activity, { compact = false } = {}) => {
        const actions = resolveDashboardActivityActions(activity);
        const busy = busyActivityIds.has(activity.id);
        if (!actions.length) {
            if (["Completed", "Approved"].includes(activity.status)) {
                return (
                    <span className="activity-completed-mark" title="Completed">
                        <span className="material-symbols-outlined">done_all</span>
                    </span>
                );
            }
            return <span className="activity-action-unavailable">—</span>;
        }

        return (
            <div className={`dashboard-activity-actions ${compact ? "compact" : ""}`}>
                {actions.map((action) => (
                    <button
                        key={action.code}
                        type="button"
                        className={`activity-workflow-button ${action.secondary ? "secondary" : ""}`}
                        title={action.label}
                        aria-label={`${action.label} for ${activity.name || activity.title || "activity"}`}
                        disabled={busy}
                        onClick={() => runDashboardActivityAction(activity, action)}
                    >
                        <span className="material-symbols-outlined" aria-hidden="true">
                            {busy && ["start", "complete"].includes(action.kind)
                                ? "progress_activity"
                                : action.icon}
                        </span>
                        {!compact && <span>{busy && ["start", "complete"].includes(action.kind) ? "Saving…" : action.label}</span>}
                    </button>
                ))}
            </div>
        );
    };

    const getCategoryClass = (category) => {
        const livestockCategories = [
            "Livestock",
            "Livestock Feeding",
            "Livestock Health Check",
            "Vaccination",
        ];

        if (livestockCategories.includes(category)) {
            return "blue";
        }

        if (
            category === "Pest Control" ||
            category === "Disease Treatment"
        ) {
            return "red";
        }

        if (
            category === "Inventory Restocking" ||
            category === "Equipment Maintenance"
        ) {
            return "orange";
        }

        return "green";
    };

    const getPriorityClass = (priority) =>
        priority.toLowerCase();

    return (
        <>
            {/* Recent activity card */}
            <article className="dashboard-card farm-activity-card">
                <div className="card-title">
                    <h3>Recent Farm Activity</h3>
                </div>

                <div className="activity-preview-list">
                    {activitiesLoading && (
                        <div className="activity-preview-item activity-preview-state">
                            <div className="activity-preview-info">
                                <strong>
                                    Loading recent activity...
                                </strong>
                            </div>
                        </div>
                    )}

                    {!activitiesLoading &&
                        activitiesError && (
                            <div className="activity-preview-item activity-preview-state">
                                <div className="activity-preview-info">
                                    <strong>
                                        Unable to load recent activity
                                    </strong>
                                    <p>{activitiesError}</p>
                                </div>
                            </div>
                        )}

                    {!activitiesLoading &&
                        !activitiesError &&
                        recentActivities.length === 0 && (
                            <div className="activity-preview-item activity-preview-state">
                                <div className="activity-preview-info">
                                    <strong>
                                        No recent farm activity
                                    </strong>
                                    <p>
                                        In-progress and completed
                                        work will appear here.
                                    </p>
                                </div>
                            </div>
                        )}

                    {!activitiesLoading &&
                        !activitiesError &&
                        recentActivities
                            .slice(0, 3)
                            .map((activity) => (
                                <div
                                    className="activity-preview-item recent-activity-item"
                                    key={activity.id}
                                >
                                    <div className="recent-activity-main">
                                        <span
                                            className={`recent-activity-icon ${activity.status
                                                .toLowerCase()
                                                .replace(
                                                    " ",
                                                    "-"
                                                )}`}
                                        >
                                            <span className="material-symbols-outlined">
                                                {activity.status ===
                                                "Completed"
                                                    ? "check"
                                                    : "schedule"}
                                            </span>
                                        </span>

                                        <div className="activity-preview-info">
                                            <strong>
                                                {
                                                    activity.name
                                                }
                                            </strong>

                                            <p>
                                                {
                                                    activity.relatedTo
                                                }
                                                {activity.location
                                                    ? ` • ${activity.location}`
                                                    : ""}
                                            </p>

                                            <span
                                                className={`recent-activity-status ${activity.status
                                                    .toLowerCase()
                                                    .replace(
                                                        " ",
                                                        "-"
                                                    )}`}
                                            >
                                                {
                                                    activity.status
                                                }
                                            </span>
                                        </div>
                                    </div>

                                    <div className="activity-preview-date">
                                        <span>
                                            {formatDate(
                                                activity.date
                                            )}
                                        </span>

                                        <small>
                                            {formatTime(
                                                activity.startTime
                                            )}
                                        </small>
                                    </div>
                                </div>
                            ))}
                </div>

                <div className="dashboard-card-footer">
                    <button
                        type="button"
                        onClick={() =>
                            setActivityModalOpen(true)
                        }
                    >
                        View All
                        <span className="material-symbols-outlined">
                            arrow_forward
                        </span>
                    </button>
                </div>
            </article>

            {/* Upcoming tasks card */}
            <article className="dashboard-card upcoming-tasks-card">
                <div className="card-title">
                    <h3>Upcoming Tasks</h3>
                </div>

                <div className="task-preview-list">
                    {activitiesLoading && (
                        <div className="task-preview-item task-preview-state">
                            <div className="task-preview-content">
                                <div>
                                    <strong>
                                        Loading pending tasks...
                                    </strong>
                                </div>
                            </div>
                        </div>
                    )}

                    {!activitiesLoading &&
                        activitiesError && (
                            <div className="task-preview-item task-preview-state">
                                <div className="task-preview-content">
                                    <div>
                                        <strong>
                                            Unable to load tasks
                                        </strong>
                                        <p>
                                            {activitiesError}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}

                    {!activitiesLoading &&
                        !activitiesError &&
                        tasks.length === 0 && (
                            <div className="task-preview-item task-preview-state">
                                <div className="task-preview-content">
                                    <div>
                                        <strong>
                                            No pending tasks
                                        </strong>
                                        <p>
                                            New scheduled work
                                            will appear here.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}

                    {!activitiesLoading &&
                        !activitiesError &&
                        tasks
                            .slice(0, 4)
                            .map((task) => {
                                const dueMeta =
                                    getTaskDueMeta(
                                        task.date
                                    );

                                return (
                                    <div
                                        className="task-preview-item"
                                        key={task.id}
                                    >
                                        <div className="task-preview-content">
                                            <span
                                                className={`task-priority-dot ${getPriorityClass(
                                                    task.priority
                                                )}`}
                                            />

                                            <div>
                                                <strong>
                                                    {
                                                        task.title
                                                    }
                                                </strong>

                                                <p>
                                                    {
                                                        task.relatedTo
                                                    }
                                                    {task.time
                                                        ? ` • ${formatTime(
                                                              task.time
                                                          )}`
                                                        : ""}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="task-preview-meta">
                                            <span
                                                className={`task-due-label ${dueMeta.className}`}
                                            >
                                                {
                                                    dueMeta.label
                                                }
                                            </span>

                                            <small
                                                className={`task-priority-text ${getPriorityClass(
                                                    task.priority
                                                )}`}
                                            >
                                                {
                                                    task.priority
                                                }
                                            </small>

                                            {renderActivityActions(task, { compact: true })}
                                        </div>
                                    </div>
                                );
                            })}
                </div>

                <div className="dashboard-card-footer">
                    <button
                        type="button"
                        onClick={() =>
                            setTaskModalOpen(true)
                        }
                    >
                        View All
                        <span className="material-symbols-outlined">
                            arrow_forward
                        </span>
                    </button>
                </div>
            </article>

            {/* Full Recent Farm Activity modal */}
            {activityModalOpen && (
                <div
                    className="activity-modal-overlay"
                    onMouseDown={() =>
                        setActivityModalOpen(false)
                    }
                >
                    <div
                        className="activity-list-modal"
                        onMouseDown={(event) =>
                            event.stopPropagation()
                        }
                    >
                        <div className="activity-modal-header">
                            <div>
                                <h2>
                                    Recent Farm Activity
                                </h2>

                                <p>
                                    Review work that is in
                                    progress or already completed.
                                </p>
                            </div>

                            <button
                                type="button"
                                onClick={() =>
                                    setActivityModalOpen(
                                        false
                                    )
                                }
                                aria-label="Close recent farm activity"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </div>

                        <div className="activity-modal-body">
                            <div className="activity-filter-box">
                                <input
                                    type="text"
                                    name="search"
                                    placeholder="Search activity..."
                                    value={
                                        activityFilters.search
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                />

                                <select
                                    name="category"
                                    value={
                                        activityFilters.category
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                >
                                    <option value="All">
                                        All categories
                                    </option>

                                    {categoryOptions.map(
                                        (category) => (
                                            <option
                                                key={
                                                    category
                                                }
                                                value={
                                                    category
                                                }
                                            >
                                                {
                                                    category
                                                }
                                            </option>
                                        )
                                    )}
                                </select>

                                <select
                                    name="location"
                                    value={
                                        activityFilters.location
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                >
                                    <option value="All">
                                        All locations
                                    </option>

                                    {locationOptions.map(
                                        (location) => (
                                            <option
                                                key={
                                                    location
                                                }
                                                value={
                                                    location
                                                }
                                            >
                                                {
                                                    location
                                                }
                                            </option>
                                        )
                                    )}
                                </select>

                                <input
                                    type="date"
                                    name="date"
                                    value={
                                        activityFilters.date
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                />

                                <select
                                    name="status"
                                    value={
                                        activityFilters.status
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                >
                                    <option value="All">
                                        All status
                                    </option>
                                    <option>
                                        In Progress
                                    </option>
                                    <option>
                                        Completed
                                    </option>
                                </select>

                                <select
                                    name="sort"
                                    value={
                                        activityFilters.sort
                                    }
                                    onChange={
                                        handleActivityFilterChange
                                    }
                                >
                                    <option>
                                        Latest
                                    </option>
                                    <option>
                                        Oldest
                                    </option>
                                    <option>
                                        A - Z
                                    </option>
                                    <option>
                                        Z - A
                                    </option>
                                </select>

                                <button
                                    type="button"
                                    className="activity-add-button"
                                    onClick={openAddActivity}
                                >
                                    <span className="material-symbols-outlined">
                                        add
                                    </span>
                                    Add Activity
                                </button>
                            </div>

                            {activityActionNotice && (
                                <div
                                    className="activity-action-notice"
                                    role="alert"
                                >
                                    <span className="material-symbols-outlined activity-action-notice-icon">
                                        warning
                                    </span>

                                    <div className="activity-action-notice-copy">
                                        <strong>
                                            Feeding was not completed
                                        </strong>
                                        <p>
                                            {activityActionNotice.activityName}
                                            {activityActionNotice.activityName
                                                ? ": "
                                                : ""}
                                            {activityActionNotice.message}
                                        </p>
                                    </div>

                                    <button
                                        type="button"
                                        className="activity-action-notice-source"
                                        title={activityActionNotice.actionLabel}
                                        aria-label={activityActionNotice.actionLabel}
                                        onClick={() =>
                                            goToPath(
                                                activityActionNotice.destination
                                            )
                                        }
                                    >
                                        <span className="material-symbols-outlined">
                                            {activityActionNotice.actionIcon}
                                        </span>
                                    </button>

                                    <button
                                        type="button"
                                        className="activity-action-notice-close"
                                        title="Dismiss warning"
                                        aria-label="Dismiss feeding inventory warning"
                                        onClick={() =>
                                            setActivityActionNotice(
                                                null
                                            )
                                        }
                                    >
                                        <span className="material-symbols-outlined">
                                            close
                                        </span>
                                    </button>
                                </div>
                            )}

                            <div className="activity-table-card">
                                <div className="activity-table-heading">
                                    <h3>
                                        Recent activity list
                                    </h3>

                                    <span>
                                        {
                                            filteredActivities.length
                                        }{" "}
                                        records
                                    </span>
                                </div>

                                <div className="activity-table-wrapper">
                                    <table className="activity-table">
                                        <thead>
                                            <tr>
                                                <th>
                                                    Activity
                                                </th>
                                                <th>
                                                    Category
                                                </th>
                                                <th>
                                                    Related To
                                                </th>
                                                <th>
                                                    Location
                                                </th>
                                                <th>
                                                    Date & Time
                                                </th>
                                                <th>
                                                    By
                                                </th>
                                                <th>
                                                    Status
                                                </th>
                                                <th>
                                                    Priority
                                                </th>
                                                <th>
                                                    Actions
                                                </th>
                                            </tr>
                                        </thead>

                                        <tbody>
                                            {filteredActivities.length >
                                            0 ? (
                                                filteredActivities.map(
                                                    (
                                                        activity
                                                    ) => (
                                                        <tr
                                                            key={
                                                                activity.id
                                                            }
                                                        >
                                                            <td>
                                                                {
                                                                    activity.name
                                                                }
                                                            </td>

                                                            <td>
                                                                <span
                                                                    className={`activity-category-badge ${getCategoryClass(
                                                                        activity.category
                                                                    )}`}
                                                                >
                                                                    {
                                                                        activity.category
                                                                    }
                                                                </span>
                                                            </td>

                                                            <td>
                                                                {
                                                                    activity.relatedTo
                                                                }
                                                            </td>

                                                            <td>
                                                                {
                                                                    activity.location
                                                                }
                                                            </td>

                                                            <td>
                                                                {formatDate(
                                                                    activity.date
                                                                )}
                                                                <small>
                                                                    {formatTime(
                                                                        activity.startTime
                                                                    )}
                                                                </small>
                                                            </td>

                                                            <td>
                                                                {
                                                                    activity.assignedBy
                                                                }
                                                            </td>

                                                            <td>
                                                                <span
                                                                    className={`activity-status-badge ${activity.status
                                                                        .toLowerCase()
                                                                        .replace(
                                                                            " ",
                                                                            "-"
                                                                        )}`}
                                                                >
                                                                    {
                                                                        activity.status
                                                                    }
                                                                </span>
                                                            </td>

                                                            <td>
                                                                <span
                                                                    className={`activity-priority-badge ${getPriorityClass(
                                                                        activity.priority
                                                                    )}`}
                                                                >
                                                                    {
                                                                        activity.priority
                                                                    }
                                                                </span>
                                                            </td>

                                                            <td>
                                                                {renderActivityActions(activity)}
                                                            </td>
                                                        </tr>
                                                    )
                                                )
                                            ) : (
                                                <tr>
                                                    <td
                                                        colSpan="9"
                                                        className="activity-empty-table"
                                                    >
                                                        No activities
                                                        found.
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Full Upcoming Tasks modal */}
            {taskModalOpen && (
                <div
                    className="activity-modal-overlay"
                    onMouseDown={() =>
                        setTaskModalOpen(false)
                    }
                >
                    <div
                        className="task-list-modal"
                        onMouseDown={(event) =>
                            event.stopPropagation()
                        }
                    >
                        <div className="activity-modal-header">
                            <div>
                                <h2>Upcoming Tasks</h2>

                                <p>
                                    Pending work that still
                                    needs attention. Start a
                                    task to move it into Recent
                                    Farm Activity.
                                </p>
                            </div>

                            <button
                                type="button"
                                onClick={() =>
                                    setTaskModalOpen(false)
                                }
                                aria-label="Close upcoming tasks"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </div>

                        <div className="task-modal-body">
                            <div className="task-modal-filters">
                                <input
                                    type="text"
                                    placeholder="Search task..."
                                    value={taskSearch}
                                    onChange={(event) =>
                                        setTaskSearch(
                                            event.target.value
                                        )
                                    }
                                />

                                <button
                                    type="button"
                                    onClick={openAddActivity}
                                >
                                    <span className="material-symbols-outlined">
                                        add
                                    </span>
                                    Add Activity
                                </button>
                            </div>

                            <div className="task-full-list">
                                {filteredTasks.length > 0 ? (
                                    filteredTasks.map(
                                        (task) => (
                                            <div
                                                className="task-full-item"
                                                key={task.id}
                                            >
                                                <span
                                                    className={`task-priority-dot ${getPriorityClass(
                                                        task.priority
                                                    )}`}
                                                />

                                                <div className="task-full-info">
                                                    <strong>
                                                        {
                                                            task.title
                                                        }
                                                    </strong>

                                                    <p>
                                                        {
                                                            task.relatedTo
                                                        }
                                                    </p>
                                                </div>

                                                <div className="task-full-date">
                                                    <span>
                                                        {formatDate(
                                                            task.date
                                                        )}
                                                    </span>

                                                    <small>
                                                        {formatTime(
                                                            task.time
                                                        )}
                                                    </small>
                                                </div>

                                                <span
                                                    className={`task-status-label ${task.status
                                                        .toLowerCase()
                                                        .replace(
                                                            " ",
                                                            "-"
                                                        )}`}
                                                >
                                                    {
                                                        task.status
                                                    }
                                                </span>

                                                {renderActivityActions(task)}
                                            </div>
                                        )
                                    )
                                ) : (
                                    <div className="task-empty">
                                        No pending tasks found.
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Add Activity form */}
        </>
    );
}

export default DashboardActivity;
