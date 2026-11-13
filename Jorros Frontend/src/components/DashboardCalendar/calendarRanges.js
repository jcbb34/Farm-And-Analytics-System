import { formatDashboardDateKey } from "../../services/dashboardPeriod.js";

export function calendarRanges(month, selected, view = "Month", expanded = false) {
    const day = new Date(selected.getFullYear(), selected.getMonth(), selected.getDate());
    const range = (start, end) => ({ date_from: formatDashboardDateKey(start), date_to: formatDashboardDateKey(end) });
    let start = new Date(month.getFullYear(), month.getMonth(), 1), end;
    if (expanded && view === "Day") start = new Date(day), end = new Date(day);
    else if (expanded && view === "Week") {
        start = new Date(day); start.setDate(start.getDate() - start.getDay());
        end = new Date(start); end.setDate(end.getDate() + 6);
    } else if (expanded && view === "Agenda") end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    else {
        // Both the Monday-first compact grid and Sunday-first full grid use
        // up to six weeks, including their adjacent-month cells.
        const sunday = new Date(start), monday = new Date(start);
        sunday.setDate(sunday.getDate() - sunday.getDay());
        monday.setDate(monday.getDate() - (monday.getDay() + 6) % 7);
        start = new Date(Math.min(sunday.getTime(), monday.getTime()));
        end = new Date(Math.max(sunday.getTime(), monday.getTime())); end.setDate(end.getDate() + 41);
    }
    const next = new Date(day), last = new Date(day);
    next.setDate(next.getDate() + 1); last.setDate(last.getDate() + 7);
    return { summary: range(start, end), day: range(day, day), upcoming: range(next, last), agenda: range(start, end) };
}
