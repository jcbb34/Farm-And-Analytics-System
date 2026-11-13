import { formatDashboardDateKey } from "../../services/dashboardPeriod.js";

export function chartRange(filter, now = new Date()) {
    const custom = /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/.exec(filter);
    if (custom) return { startDate: custom[1], endDate: custom[2] };
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(start);
    const monday = () => start.setDate(start.getDate() - (start.getDay() === 0 ? 6 : start.getDay() - 1));
    if (filter === "This Week" || filter === "Last Week") {
        monday();
        if (filter === "Last Week") start.setDate(start.getDate() - 7);
        end.setTime(start.getTime()); end.setDate(end.getDate() + 6);
    } else if (filter === "This Month" || filter === "Last Month") {
        start.setDate(1);
        if (filter === "Last Month") start.setMonth(start.getMonth() - 1);
        end.setFullYear(start.getFullYear(), start.getMonth() + 1, 0);
    } else if (filter === "Last 7 Days") start.setDate(start.getDate() - 6);
    else if (filter === "Last 30 Days") start.setDate(start.getDate() - 29);
    else if (filter === "This Year") { start.setMonth(0, 1); end.setMonth(11, 31); }
    return { startDate: formatDashboardDateKey(start), endDate: formatDashboardDateKey(end) };
}
