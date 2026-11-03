export const DEFAULT_TASK_VIEW = "active";
export const DEFAULT_SCHEDULE_FILTER = "timeline";

export const TASK_VIEW_OPTIONS = Object.freeze([
    ["active", "Active Tasks"],
    ["pending", "Pending"],
    ["in-progress", "In Progress"],
    ["returned", "Returned"],
    ["review", "For Review"],
    ["completed", "Completed History"],
    ["history", "Task History"],
    ["all", "All Tasks"],
]);

export const ACTIVE_TASK_STATUSES = new Set([
    "Pending",
    "In Progress",
    "Returned",
    "Submitted for Review",
]);

export const HISTORY_TASK_STATUSES = new Set([
    "Completed",
    "Approved",
    "Voided",
    "Cancelled",
    "Resolved",
]);

const MISSED_TASK_STATUSES = new Set(["Pending", "In Progress", "Returned"]);

export function apiViewForTaskView(taskView) {
    if (taskView === "completed") return "completed";
    if (taskView === "history") return "history";
    if (taskView === "all") return "all";
    return "active";
}

export function matchesTaskView(task, taskView) {
    switch (taskView) {
        case "active": return ACTIVE_TASK_STATUSES.has(task?.status);
        case "pending": return task?.status === "Pending";
        case "in-progress": return task?.status === "In Progress";
        case "returned": return task?.status === "Returned";
        case "review": return task?.status === "Submitted for Review";
        case "completed": return task?.status === "Completed" && !task?.is_archived;
        case "history": return Boolean(task?.is_archived) || HISTORY_TASK_STATUSES.has(task?.status);
        case "all": return true;
        default: return ACTIVE_TASK_STATUSES.has(task?.status);
    }
}

export function isMissedTaskForView(task, todayKey) {
    return Boolean(!task?.work_suspended && task?.activity_date && task.activity_date < todayKey && MISSED_TASK_STATUSES.has(task.status));
}

export function isFutureTaskForView(task, todayKey) {
    return Boolean(task?.activity_date && todayKey && String(task.activity_date) > String(todayKey));
}

export function canWorkTaskForView(task, todayKey) {
    if (!task || task.work_suspended || task.is_archived || isFutureTaskForView(task, todayKey)) return false;
    return ["Pending", "In Progress", "Returned"].includes(task.status);
}

export function completionTimestamp(task) {
    const submission = task?.latest_submission;
    const approvedFallback = submission?.review_status === "Approved"
        ? (submission.reviewed_at || submission.submitted_at)
        : null;
    const rawValue = task?.completed_at || approvedFallback;
    if (!rawValue) return 0;
    const parsed = new Date(rawValue).getTime();
    return Number.isFinite(parsed) ? parsed : 0;
}

export function scheduleForTaskViewChange(currentView, nextView, currentSchedule) {
    if (["completed", "history", "all"].includes(nextView)) return "all";
    if (["completed", "history", "all"].includes(currentView)) return DEFAULT_SCHEDULE_FILTER;
    return currentSchedule;
}

function matchesSearch(task, query) {
    if (!query) return true;
    const haystack = [
        task?.name,
        task?.activity_code,
        task?.code,
        task?.location,
        task?.description,
        task?.instructions,
        task?.status,
        task?.priority,
        task?.planned_inventory_item_name,
        task?.planned_unit,
        task?.planned_inventory_unit,
        task?.latest_submission?.worker_notes,
        task?.latest_submission?.review_feedback,
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(query);
}

export function filterAndSortMyTasks({
    tasks,
    taskView,
    searchTerm,
    priorityFilter,
    scheduleFilter,
    selectedDateKey = null,
    todayKey,
    upcomingLimitKey,
}) {
    const query = String(searchTerm || "").trim().toLowerCase();
    const filtered = (tasks || []).filter((task) => {
        if (!matchesTaskView(task, taskView)) return false;
        if (!matchesSearch(task, query)) return false;
        if (priorityFilter !== "all" && task.priority !== priorityFilter) return false;

        // Active Timeline is deliberately bounded to overdue/current work plus
        // the next seven days. Far-future recurring occurrences are available
        // through the explicit All Active Dates filter instead of slowing the
        // initial My Tasks load.
        if (scheduleFilter === "timeline" && task.activity_date > upcomingLimitKey) return false;
        if (scheduleFilter === "today" && task.activity_date !== todayKey) return false;
        if (scheduleFilter === "upcoming" && !(task.activity_date > todayKey && task.activity_date <= upcomingLimitKey)) return false;
        if (scheduleFilter === "overdue" && !isMissedTaskForView(task, todayKey)) return false;
        if (scheduleFilter === "date" && (!selectedDateKey || task.activity_date !== selectedDateKey)) return false;

        return true;
    });

    if (["completed", "history"].includes(taskView)) {
        return filtered.sort((left, right) => {
            const completionDifference = completionTimestamp(right) - completionTimestamp(left);
            if (completionDifference) return completionDifference;
            const dateDifference = String(right.activity_date || "").localeCompare(String(left.activity_date || ""));
            if (dateDifference) return dateDifference;
            return Number(right.id || 0) - Number(left.id || 0);
        });
    }

    const rank = (task) => {
        if (task.status === "Returned") return 0;
        if (isMissedTaskForView(task, todayKey)) return 1;
        if (task.activity_date === todayKey && task.status !== "Submitted for Review") return 2;
        if (task.status === "In Progress") return 3;
        if (task.status === "Submitted for Review") return 4;
        if (task.activity_date > todayKey) return 5;
        return 6;
    };

    return filtered.sort((left, right) => {
        const rankDifference = rank(left) - rank(right);
        if (rankDifference) return rankDifference;
        return String(left.activity_date || "").localeCompare(String(right.activity_date || ""))
            || String(left.start_time || "").localeCompare(String(right.start_time || ""));
    });
}
