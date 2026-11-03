const MANAGER_ACTIONS = Object.freeze({
    resolve_assignment: {
        label: "Resolve Assignment",
        icon: "assignment_late",
        taskView: "active",
        assignmentState: "needs-reassignment",
    },
    review_submission: {
        label: "Review Submission",
        icon: "rate_review",
        taskView: "review",
    },
    view_returned_task: {
        label: "View Returned Task",
        icon: "assignment_return",
        taskView: "returned",
    },
    view_report: {
        label: "View Report",
        icon: "description",
        taskView: "history",
    },
    open_task: {
        label: "Open Task",
        icon: "open_in_new",
        taskView: "active",
    },
    assisted_submission: {
        label: "Record Work",
        icon: "fact_check",
        taskView: "active",
        assisted: true,
    },
});

const EMPLOYEE_ACTIONS = Object.freeze({
    open_my_tasks: {
        label: "Open in My Tasks",
        icon: "task_alt",
        taskView: "active",
    },
    correct_submission: {
        label: "Correct Submission",
        icon: "edit_note",
        taskView: "returned",
    },
    view_submission: {
        label: "View Submission",
        icon: "visibility",
        taskView: "review",
    },
    view_history: {
        label: "View History",
        icon: "history",
        taskView: "history",
    },
});

export function buildTaskManagementPath(activity, actionCode = "open_task") {
    const linkedTaskId = Number(activity?.linkedTaskId || 0);
    if (!linkedTaskId) return "/task-management?tab=tasks";
    const config = MANAGER_ACTIONS[actionCode] || MANAGER_ACTIONS.open_task;
    const params = new URLSearchParams({
        tab: "tasks",
        taskId: String(linkedTaskId),
        from: "dashboard",
        returnTo: "/dashboard",
    });
    if (config.assignmentState) params.set("assignmentState", config.assignmentState);
    if (config.assisted) params.set("action", "assisted-submission");
    return `/task-management?${params.toString()}`;
}

export function buildMyTasksPath(activity, actionCode = "open_my_tasks") {
    const linkedTaskId = Number(activity?.linkedTaskId || 0);
    const config = EMPLOYEE_ACTIONS[actionCode] || EMPLOYEE_ACTIONS.open_my_tasks;
    const params = new URLSearchParams({
        tab: "tasks",
        taskId: linkedTaskId ? String(linkedTaskId) : "",
        view: config.taskView,
        schedule: "all",
        from: "dashboard",
        returnTo: "/dashboard",
    });
    if (!linkedTaskId) params.delete("taskId");
    return `/my-tasks?${params.toString()}`;
}

export function activityRequiresTaskWorkflow(activity) {
    return Boolean(
        isTaskWorkflowActivity(activity) ||
        activity?.assignedEmployeeId != null ||
        activity?.requiresReview ||
        activity?.requiresEmployeeSubmission ||
        activity?.requiresManagerReview
    );
}

export function resolveDashboardActivityActions(activity) {
    const available = Array.isArray(activity?.availableActions)
        ? activity.availableActions
        : [];
    const actions = [];
    const taskProtected = activityRequiresTaskWorkflow(activity);

    for (const code of available) {
        if (MANAGER_ACTIONS[code]) {
            const config = MANAGER_ACTIONS[code];
            actions.push({
                code,
                label: config.label,
                icon: config.icon,
                kind: "navigate",
                path: buildTaskManagementPath(activity, code),
                secondary: code === "assisted_submission",
            });
            continue;
        }
        if (EMPLOYEE_ACTIONS[code]) {
            const config = EMPLOYEE_ACTIONS[code];
            actions.push({
                code,
                label: config.label,
                icon: config.icon,
                kind: "navigate",
                path: buildMyTasksPath(activity, code),
            });
            continue;
        }
        if (
            code === "start_directly" &&
            activity?.canCompleteDirectly &&
            !taskProtected &&
            !activity?.isAutomatic
        ) {
            actions.push({
                code,
                label: "Start",
                icon: "play_arrow",
                kind: "start",
            });
            continue;
        }
        if (
            code === "complete_directly" &&
            activity?.canCompleteDirectly &&
            !taskProtected &&
            !activity?.isAutomatic
        ) {
            actions.push({
                code,
                label: "Complete",
                icon: "check",
                kind: "complete",
            });
            continue;
        }
        if (code === "open_source" && activity?.sourcePath) {
            actions.push({
                code,
                label: "Open Source",
                icon: "open_in_new",
                kind: "navigate",
                path: activity.sourcePath,
            });
        }
    }

    return actions;
}

export function isTaskWorkflowActivity(activity) {
    return ["workforce_task", "care_task"].includes(activity?.workflowType);
}
