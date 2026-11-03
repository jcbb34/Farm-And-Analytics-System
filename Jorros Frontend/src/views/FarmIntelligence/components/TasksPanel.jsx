"use client";

import {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "../../../context/AuthContext.jsx";
import {
    notifyError,
    notifySuccess,
    notifyWarning,
} from "../../../context/NotificationContext.jsx";
import {
    addTimelineEntry,
    logAudit,
} from "../../../services/farmIntelligenceService.js";
import { activityService } from "../../../services/activityService.js";

// Task date helpers
function getTodayKey() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(
        now.getMonth() + 1
    ).padStart(2, "0");
    const day = String(
        now.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function getTaskDisplayStatus(task) {
    const dueDate =
        task.date ||
        task.dueDate ||
        "";

    if (
        !["Completed", "Cancelled", "Resolved", "Voided"].includes(
            task.status
        ) &&
        dueDate &&
        dueDate < getTodayKey()
    ) {
        return "Overdue";
    }

    return task.status;
}

// Task assignment form and shared task list
function TasksPanel({ canEdit }) {
    const router = useRouter();
    const { user } = useAuth();

    const [tasks, setTasks] =
        useState([]);
    const [loading, setLoading] =
        useState(true);
    const [loadError, setLoadError] =
        useState("");
    const [saving, setSaving] =
        useState(false);

    const [form, setForm] = useState({
        title: "",
        module: "Crop",
        relatedRecord: "",
        assignedTo: "",
        dueDate: getTodayKey(),
        dueTime: "08:00",
        priority: "Medium",
        notes: "",
    });

    const loadTasks = useCallback(
        async () => {
            try {
                setLoading(true);
                setLoadError("");

                const records =
                    await activityService.getActivities(
                        false
                    );

                setTasks(
                    records.filter(
                        (record) =>
                            record.status !==
                            "Cancelled"
                    )
                );
            } catch (error) {
                console.error(
                    "Failed to load assigned tasks:",
                    error
                );

                setLoadError(
                    error?.message ||
                        "Unable to load assigned tasks."
                );
            } finally {
                setLoading(false);
            }
        },
        []
    );

    useEffect(() => {
        loadTasks();

        const refresh = () => {
            loadTasks();
        };

        window.addEventListener(
            "joross:activities-updated",
            refresh
        );

        return () => {
            window.removeEventListener(
                "joross:activities-updated",
                refresh
            );
        };
    }, [loadTasks]);

    const handleChange = (event) => {
        const { name, value } =
            event.target;

        setForm((current) => ({
            ...current,
            [name]: value,
        }));
    };

    const sourcePathForModule = (
        module
    ) => {
        if (module === "Crop") {
            return "/crops";
        }

        if (module === "Livestock") {
            return "/livestock";
        }

        if (module === "Inventory") {
            return "/inventory";
        }

        return "";
    };

    const categoryForModule = (
        module
    ) => {
        if (module === "Crop") {
            return "Farm Inspection";
        }

        if (module === "Livestock") {
            return "Livestock";
        }

        if (module === "Inventory") {
            return "Inventory Restocking";
        }

        return "Other";
    };

    const addTask = async (event) => {
        event.preventDefault();

        if (!canEdit || saving) {
            return;
        }

        if (
            !form.title.trim() ||
            !form.assignedTo.trim()
        ) {
            notifyWarning(
                "Task name and assigned person are required."
            );
            return;
        }

        try {
            setSaving(true);

            const task =
                await activityService.createActivity(
                    {
                        name:
                            form.title.trim(),
                        category:
                            categoryForModule(
                                form.module
                            ),
                        relatedTo:
                            form.relatedRecord.trim() ||
                            `${form.module} Task`,
                        location:
                            form.relatedRecord.trim() ||
                            "Jorros Farm",
                        description:
                            form.notes.trim(),
                        date:
                            form.dueDate,
                        startTime:
                            form.dueTime,
                        assignedBy:
                            user?.fullName ||
                            user?.name ||
                            "Farm Intelligence",
                        assignedTo:
                            form.assignedTo.trim(),
                        status: "Pending",
                        priority:
                            form.priority,
                        sourceModule:
                            form.module,
                        sourceType:
                            "manual_assignment",
                        sourcePath:
                            sourcePathForModule(
                                form.module
                            ),
                    }
                );

            setTasks((current) => [
                task,
                ...current.filter(
                    (item) =>
                        item.id !== task.id
                ),
            ]);

            logAudit({
                action:
                    "Assigned farm task",
                module:
                    form.module,
                recordName:
                    form.relatedRecord.trim() ||
                    form.title.trim(),
                entityId:
                    task.activityCode ||
                    task.id,
                details:
                    `${task.name} assigned to ${task.assignedTo}.`,
            });

            addTimelineEntry({
                module:
                    form.module,
                recordName:
                    form.relatedRecord.trim() ||
                    form.title.trim(),
                entityId:
                    task.activityCode ||
                    task.id,
                title:
                    "Farm task assigned",
                details:
                    `${task.name} • ${task.assignedTo}`,
                icon: "assignment",
            });

            setForm((current) => ({
                ...current,
                title: "",
                relatedRecord: "",
                assignedTo: "",
                notes: "",
            }));

            notifySuccess(
                "Farm task assigned successfully."
            );
        } catch (error) {
            console.error(
                "Failed to assign task:",
                error
            );

            notifyError(
                error?.message ||
                    "Unable to assign the farm task."
            );
        } finally {
            setSaving(false);
        }
    };

    const setTaskStatus = async (
        taskId,
        status
    ) => {
        const task = tasks.find(
            (item) =>
                item.id === taskId
        );

        if (!task || !canEdit) {
            return;
        }

        try {
            const updated =
                await activityService.updateActivity(
                    taskId,
                    {
                        status,
                    }
                );

            setTasks((current) =>
                current.map((item) =>
                    item.id === taskId
                        ? updated
                        : item
                )
            );

            logAudit({
                action:
                    "Updated task status",
                module:
                    task.sourceModule ||
                    task.category,
                recordName:
                    task.relatedTo ||
                    task.name,
                entityId:
                    task.activityCode ||
                    task.id,
                details:
                    `${task.name}: ${status}.`,
            });

            notifySuccess(
                status === "In Progress"
                    ? "Task started."
                    : "Task completed."
            );
        } catch (error) {
            console.error(
                "Failed to update task status:",
                error
            );

            notifyError(
                error?.message ||
                    "Unable to update the task."
            );
        }
    };

    const taskQueue = useMemo(
        () => {
            const order = {
                Pending: 0,
                "In Progress": 1,
                Completed: 2,
            };

            return [...tasks].sort(
                (first, second) => {
                    const firstRank =
                        order[
                            first.status
                        ] ?? 9;

                    const secondRank =
                        order[
                            second.status
                        ] ?? 9;

                    if (
                        firstRank !==
                        secondRank
                    ) {
                        return (
                            firstRank -
                            secondRank
                        );
                    }

                    return String(
                        first.date || ""
                    ).localeCompare(
                        String(
                            second.date || ""
                        )
                    );
                }
            );
        },
        [tasks]
    );

    const canCompleteDirectly = (
        task
    ) =>
        !task.isAutomatic ||
        task.sourceType ===
            "livestock_feeding";

    return (
        <div className="fi-two-column">
            <section className="fi-card">
                <div className="fi-section-heading">
                    <div>
                        <h3>
                            Task Assignment
                        </h3>
                        <p>
                            Assign work here. The same task
                            appears in Dashboard Upcoming Tasks.
                            Crop, livestock, and inventory
                            actions are also synchronized
                            automatically.
                        </p>
                    </div>
                </div>

                <form
                    className="fi-form-grid single"
                    onSubmit={addTask}
                >
                    <label>
                        <span>
                            Task Name *
                        </span>
                        <input
                            name="title"
                            value={
                                form.title
                            }
                            onChange={
                                handleChange
                            }
                            placeholder="Example: Inspect irrigation line"
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    <label>
                        <span>Module</span>
                        <select
                            name="module"
                            value={
                                form.module
                            }
                            onChange={
                                handleChange
                            }
                            disabled={
                                !canEdit ||
                                saving
                            }
                        >
                            <option>
                                Crop
                            </option>
                            <option>
                                Livestock
                            </option>
                            <option>
                                Inventory
                            </option>
                            <option>
                                System
                            </option>
                        </select>
                    </label>

                    <label>
                        <span>
                            Related Record
                        </span>
                        <input
                            name="relatedRecord"
                            value={
                                form.relatedRecord
                            }
                            onChange={
                                handleChange
                            }
                            placeholder="Example: Corn Field 1"
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    <label>
                        <span>
                            Assigned To *
                        </span>
                        <input
                            name="assignedTo"
                            value={
                                form.assignedTo
                            }
                            onChange={
                                handleChange
                            }
                            placeholder="Employee or role"
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    <label>
                        <span>
                            Due Date
                        </span>
                        <input
                            type="date"
                            name="dueDate"
                            value={
                                form.dueDate
                            }
                            onChange={
                                handleChange
                            }
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    <label>
                        <span>
                            Due Time
                        </span>
                        <input
                            type="time"
                            name="dueTime"
                            value={
                                form.dueTime
                            }
                            onChange={
                                handleChange
                            }
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    <label>
                        <span>
                            Priority
                        </span>
                        <select
                            name="priority"
                            value={
                                form.priority
                            }
                            onChange={
                                handleChange
                            }
                            disabled={
                                !canEdit ||
                                saving
                            }
                        >
                            <option>Low</option>
                            <option>
                                Medium
                            </option>
                            <option>High</option>
                            <option>
                                Critical
                            </option>
                        </select>
                    </label>

                    <label className="full">
                        <span>Notes</span>
                        <textarea
                            rows="4"
                            name="notes"
                            value={
                                form.notes
                            }
                            onChange={
                                handleChange
                            }
                            disabled={
                                !canEdit ||
                                saving
                            }
                        />
                    </label>

                    {canEdit && (
                        <div className="fi-form-actions">
                            <button
                                type="submit"
                                className="fi-primary-button"
                                disabled={
                                    saving
                                }
                            >
                                <span className="material-symbols-outlined">
                                    add_task
                                </span>
                                {saving
                                    ? "Assigning..."
                                    : "Assign Task"}
                            </button>
                        </div>
                    )}
                </form>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>
                            Assigned Tasks
                        </h3>
                        <p>
                            One shared task queue for Dashboard,
                            Crop, Livestock, Inventory, and Farm
                            Intelligence.
                        </p>
                    </div>

                    <span className="fi-count-chip">
                        {loading
                            ? "Loading..."
                            : `${taskQueue.length} tasks`}
                    </span>
                </div>

                {loadError && (
                    <div className="fi-disclaimer">
                        <span className="material-symbols-outlined">
                            warning
                        </span>
                        <span>
                            {loadError}
                        </span>
                    </div>
                )}

                <div className="fi-task-list">
                    {!loading &&
                        taskQueue.length ===
                            0 && (
                        <article className="fi-task-card">
                            <div className="fi-task-header">
                                <div>
                                    <h4>
                                        No assigned tasks
                                    </h4>
                                    <p>
                                        New assignments and
                                        automatic farm tasks
                                        will appear here.
                                    </p>
                                </div>
                            </div>
                        </article>
                    )}

                    {taskQueue.map(
                        (task) => {
                            const status =
                                getTaskDisplayStatus(
                                    task
                                );

                            const statusClass =
                                status
                                    .toLowerCase()
                                    .replaceAll(
                                        " ",
                                        "-"
                                    );

                            return (
                                <article
                                    key={
                                        task.id
                                    }
                                    className="fi-task-card"
                                >
                                    <div className="fi-task-header">
                                        <div>
                                            <h4>
                                                {
                                                    task.name
                                                }
                                            </h4>
                                            <p>
                                                {task.relatedTo ||
                                                    task.sourceModule ||
                                                    task.category}
                                            </p>
                                        </div>

                                        <span
                                            className={`fi-task-status ${statusClass}`}
                                        >
                                            {
                                                status
                                            }
                                        </span>
                                    </div>

                                    <div className="fi-task-meta">
                                        <span>
                                            <span className="material-symbols-outlined">
                                                person
                                            </span>
                                            {
                                                task.assignedTo
                                            }
                                        </span>

                                        <span>
                                            <span className="material-symbols-outlined">
                                                event
                                            </span>
                                            {
                                                task.date
                                            }{" "}
                                            {
                                                task.startTime
                                            }
                                        </span>

                                        <span>
                                            <span className="material-symbols-outlined">
                                                priority_high
                                            </span>
                                            {
                                                task.priority
                                            }
                                        </span>
                                    </div>

                                    <div className="fi-task-meta">
                                        <span>
                                            <span className="material-symbols-outlined">
                                                hub
                                            </span>
                                            {task.sourceModule ||
                                                "General Farm"}
                                        </span>

                                        <span>
                                            <span className="material-symbols-outlined">
                                                {task.isAutomatic
                                                    ? "automation"
                                                    : "person_edit"}
                                            </span>
                                            {task.isAutomatic
                                                ? "Automatic"
                                                : "Manual"}
                                        </span>

                                        {task.sourceCode && (
                                            <span>
                                                <span className="material-symbols-outlined">
                                                    tag
                                                </span>
                                                {
                                                    task.sourceCode
                                                }
                                            </span>
                                        )}
                                    </div>

                                    {task.description && (
                                        <p className="fi-task-notes">
                                            {
                                                task.description
                                            }
                                        </p>
                                    )}

                                    {canEdit &&
                                        task.status ===
                                            "Pending" && (
                                        <button
                                            type="button"
                                            className="fi-complete-button"
                                            onClick={() =>
                                                setTaskStatus(
                                                    task.id,
                                                    "In Progress"
                                                )
                                            }
                                        >
                                            <span className="material-symbols-outlined">
                                                play_arrow
                                            </span>
                                            Start Task
                                        </button>
                                    )}

                                    {canEdit &&
                                        task.status ===
                                            "In Progress" &&
                                        canCompleteDirectly(
                                            task
                                        ) && (
                                        <button
                                            type="button"
                                            className="fi-complete-button"
                                            onClick={() =>
                                                setTaskStatus(
                                                    task.id,
                                                    "Completed"
                                                )
                                            }
                                        >
                                            <span className="material-symbols-outlined">
                                                check
                                            </span>
                                            Mark Complete
                                        </button>
                                    )}

                                    {task.sourcePath &&
                                        task.isAutomatic &&
                                        task.sourceType !==
                                            "livestock_feeding" &&
                                        task.status !==
                                            "Completed" && (
                                        <button
                                            type="button"
                                            className="fi-secondary-button"
                                            onClick={() =>
                                                router.push(
                                                    task.sourcePath
                                                )
                                            }
                                        >
                                            <span className="material-symbols-outlined">
                                                open_in_new
                                            </span>
                                            Open{" "}
                                            {
                                                task.sourceModule
                                            }
                                        </button>
                                    )}
                                </article>
                            );
                        }
                    )}
                </div>
            </section>
        </div>
    );
}

export default TasksPanel;
