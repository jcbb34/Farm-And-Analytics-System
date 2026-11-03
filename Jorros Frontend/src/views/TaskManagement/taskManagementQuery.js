function addDaysToDateKey(key, days) {
    const [year, month, day] = String(key).split("-").map(Number);
    const value = new Date(year, month - 1, day);
    value.setDate(value.getDate() + days);
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}


export function buildTaskManagementQuery({
    taskDateFilter = "",
    taskScheduleFilter = "Actionable Now",
    taskStatusFilter = "All",
    taskEmployeeFilter = "All",
    taskPriorityFilter = "All",
    taskReassignmentFilter = "All",
    taskSearch = "",
    todayKey,
}) {
    let query;

    if (taskDateFilter) {
        query = { date_from: taskDateFilter, date_to: taskDateFilter };
    } else if (taskScheduleFilter === "Actionable Now") {
        query = { actionable_only: true };
    } else if (taskScheduleFilter === "Today") {
        query = { date_from: todayKey, date_to: todayKey };
    } else if (taskScheduleFilter === "Missed / Overdue") {
        query = { date_to: addDaysToDateKey(todayKey, -1), open_only: true };
    } else if (taskScheduleFilter === "Upcoming") {
        query = { date_from: addDaysToDateKey(todayKey, 1), open_only: true };
    } else if (taskScheduleFilter === "Next 7 Days") {
        query = {
            date_from: addDaysToDateKey(todayKey, 1),
            date_to: addDaysToDateKey(todayKey, 7),
            open_only: true,
        };
    } else {
        query = {};
    }

    // "Missed" is a derived browser-side state, not a database status.
    if (taskStatusFilter && !["All", "Missed"].includes(taskStatusFilter)) {
        query.status = taskStatusFilter;
    }

    // Send a concrete employee selection to the API. "All" and "Unassigned"
    // continue to use the existing client-side behavior.
    const employeeValue = String(taskEmployeeFilter || "");
    if (/^[1-9]\d*$/.test(employeeValue)) {
        query.employee_id = Number(employeeValue);
    }
    if (taskEmployeeFilter === "Unassigned") query.assignment_state = "Unassigned";
    if (taskPriorityFilter !== "All") query.priority = taskPriorityFilter;
    if (taskReassignmentFilter !== "All") query.assignment_state = taskReassignmentFilter;
    if (taskSearch.trim()) query.search = taskSearch.trim();

    return query;
}
