export function buildMyTasksPageQuery({
    view, scope, taskView, search, priorityFilter, scheduleFilter,
    selectedTaskDate, todayKey, upcomingLimitKey, sharedDevice,
}) {
    const query = { view, scope, limit: 25, shared_device: sharedDevice };
    const statuses = {
        pending: "Pending", "in-progress": "In Progress", returned: "Returned",
        review: "Submitted for Review",
    };
    if (statuses[taskView]) query.status_filter = statuses[taskView];
    if (priorityFilter !== "all") query.priority = priorityFilter;
    if (search.trim()) query.search = search.trim();
    if (scheduleFilter === "today") query.date_from = query.date_to = todayKey;
    if (scheduleFilter === "date" && selectedTaskDate) query.date_from = query.date_to = selectedTaskDate;
    if (scheduleFilter === "upcoming") {
        query.date_from = addCalendarDays(todayKey, 1);
        query.date_to = upcomingLimitKey;
    }
    if (scheduleFilter === "overdue") query.missed_only = true;
    return query;
}
import { addCalendarDays } from "../../utils/farmCalendar.js";
